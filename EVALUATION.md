# System Design & Evaluation Notes

## 1. Orchestration pattern: LangGraph (and why)

This project uses **LangGraph** rather than AutoGen for the reasoning
engine, for three reasons specific to this task:

1. **Explicit, inspectable control flow.** LangGraph models the workflow as
   a graph of nodes (`planner`, `researcher`, `synthesizer`) and edges,
   including a *conditional* edge (`route_after_researcher`) that loops the
   Researcher node once per plan step before advancing to the Synthesizer.
   This maps directly onto the requirement to "define explicit transition
   rules that govern how control passes" between agents — the routing
   function is a single, testable piece of logic (`app/agents/graph.py`),
   rather than being implicit in a chat-style multi-agent conversation.

2. **A single, explicit shared state object.** `AgentState` (a `TypedDict`
   in `app/agents/state.py`) holds `prompt`, `plan`, `step_index`,
   `research_results`, and `final_result`. Every node reads only what it
   needs and returns a partial update; LangGraph merges it. This makes the
   audit trail predictable: at any point we can say exactly what each agent
   saw and produced.

3. **Natural fit for looping, tool-augmented steps.** AutoGen's strength is
   free-form multi-agent conversation; this task instead has a fixed
   pipeline shape (plan → do N research steps → synthesize), which
   LangGraph's graph/loop model expresses more directly and predictably
   than a conversational pattern would.

The LLM itself is provider-agnostic: `app/agents/llm.py` exposes one
`get_llm()` factory, switched via the `LLM_PROVIDER` env var
(`openai` or `anthropic`), so every agent automatically uses whichever
provider is configured without any per-agent code changes.

## 2. Agent roles and system prompts

All three agents share one LLM instance but are given entirely different
system prompts (see `app/agents/prompts.py`), which is what gives them
distinct behavior:

### Planner (`PLANNER_SYSTEM_PROMPT`)
- **Responsibility**: decompose the user's raw prompt into 1–4 concrete,
  independently executable research steps.
- **Output contract**: a JSON array of strings, nothing else.
- **Failure handling**: if the LLM returns malformed JSON or an empty list,
  `planner_node` falls back to a single-step plan containing the original
  prompt verbatim, so the workflow can never dead-end on a parsing failure.

### Researcher (`RESEARCHER_SYSTEM_PROMPT`)
- **Responsibility**: given ONE step at a time, decide whether a tool is
  needed and which one, then actually invoke it (via Celery) and record
  the result.
- **Output contract**: a JSON object `{"tool", "arguments", "reasoning"}`.
- **Loop behavior**: `route_after_researcher` sends control back to this
  same node for every remaining plan step before moving on, incrementing
  `step_index` each pass — this is the "loop through the Researcher node N
  times" behavior called for in the brief.

### Synthesizer (`SYNTHESIZER_SYSTEM_PROMPT`)
- **Responsibility**: combine the original prompt with every accumulated
  `research_results` entry (including any tool errors) into one coherent,
  final prose answer.
- **Failure handling**: explicitly instructed to acknowledge — not
  paper over — any research step that failed, rather than inventing data.

## 3. Shared state management

`AgentState` is intentionally a plain `TypedDict` rather than relying on
LangGraph's `Annotated[list, operator.add]` reducer sugar. Each node
receives the *whole* current state, does its own read of what it needs
(e.g. `state["plan"][state["step_index"]]`), and returns only the fields it
changed. This keeps the data flow easy to reason about and easy to log:
`app/agents/runner.py`'s `emit()` closure is called from inside every node
with a structured payload, so state changes and the audit log are always in
sync by construction (there's no separate "reflect state into events" pass
that could drift out of sync).

## 4. Custom tools: schemas, outputs, and error handling

All three tools live in `app/tools/`, split cleanly into:
- `schemas.py` — Pydantic input models with rich `Field(description=...)`
  text, which is what actually gets shown to the LLM.
- `logic.py` — the real implementation, wrapped defensively.
- `tasks.py` — thin `@celery_app.task` wrappers so execution can be
  offloaded to a worker process.

| Tool | Input schema | Success output | Error handling |
|---|---|---|---|
| `web_search` | `query: str`, `max_results: int` (Brave Search API) | Formatted list of `title / description / url` | Missing API key, `HTTPStatusError`, `RequestError`, and any unexpected exception are each caught separately and turned into a distinct, agent-readable `"Error: ..."` string with a suggested next action. |
| `weather_lookup` | `location: str`, `units: "metric"\|"imperial"` (OpenWeatherMap) | Human-readable current conditions string | Missing API key, 404 (unknown location) handled specially vs. other HTTP errors, network errors, and malformed-response `KeyError`/`IndexError` are all caught individually. |
| `calculation` | `expression: str` | Numeric result, explained in a sentence | Uses `simpleeval` (a sandboxed evaluator — never raw `eval()`) so malformed or unsafe expressions raise `InvalidExpression`, which is caught and returned as a corrective error string; `ZeroDivisionError` is also caught explicitly. |

**Design principle applied everywhere**: a tool never raises an exception
out to the caller. Every failure path returns a *string* the agent can
read and react to (e.g. "Suggest continuing without this data"), which is
what allows the Researcher/Synthesizer to gracefully degrade instead of the
whole workflow crashing — this was verified manually by leaving
`OPENWEATHER_API_KEY` unset and confirming the run still completes with a
`COMPLETED` status and a final answer that acknowledges the missing data.

Each Celery task wrapper additionally has its own top-level
`try/except` as a last-resort safety net, so even a bug inside the wrapper
itself (not just the underlying API call) can't crash a worker process.

## 5. Persistence & auditability strategy

Two tables, defined with SQLAlchemy in `app/db/models.py`:

- **`task_runs`**: one row per submitted prompt — `id` (UUID), `prompt`,
  `status` (`PENDING → IN_PROGRESS → COMPLETED`/`FAILED`), `final_result`,
  timestamps.
- **`agent_events`**: one row per discrete thing that happened —
  `task_run_id` (FK), `agent_name`, `event_type` (`AGENT_THOUGHT`,
  `TOOL_INVOCATION`, `TOOL_RESULT`, `ERROR`, `FINAL_RESULT`,
  `STATUS_CHANGE`), a JSON `payload`, and a `timestamp`.

Every call to `emit()` in `app/agents/runner.py` does two things in
lockstep: write the event to Postgres, then publish the same payload to a
Redis pub/sub channel (`ws:{task_id}`). This means the audit log in the
database and what the browser sees over the WebSocket are always identical
by construction — there is exactly one code path that produces an event.

## 6. Asynchronous architecture rationale

- **Why Celery for tools, not just `asyncio`**: tool calls hit third-party
  HTTP APIs with unpredictable latency. Running them as Celery tasks means
  a slow or hung external API can never block the FastAPI event loop that
  is simultaneously responsible for keeping WebSocket connections (and
  their heartbeats) alive. `_run_celery_tool()` still awaits the result
  without blocking the loop, by running the blocking `AsyncResult.get()`
  call inside `asyncio.to_thread`.
- **Why the agent graph itself runs as an asyncio background task (not a
  Celery task)**: the graph needs to publish live events as it goes and
  the FastAPI process already owns the WebSocket connections and the
  Redis publisher; running the *orchestration* in-process (while
  delegating only the *slow I/O* to Celery) keeps the "who publishes
  events" responsibility in one place.
- **Why Redis pub/sub (not just an in-memory dict) bridges the workflow to
  the WebSocket**: it keeps the design correct even if the API were scaled
  to multiple replicas — any replica holding the WebSocket connection for
  a task can receive that task's events regardless of which replica
  happens to be running the workflow.
- **WebSocket resilience**: the endpoint replays all previously-logged
  events on connect (so a client that connects slightly late isn't missing
  history) and sends a `PING` heartbeat every 20 seconds so intermediate
  proxies/browsers don't treat a long tool call as a dead connection.

## 7. Known limitations / possible extensions

- Table creation uses `Base.metadata.create_all` on startup rather than
  Alembic migrations — appropriate for this project's scope, but a real
  production system would use versioned migrations.
- The Planner is capped at 4 steps and the graph has a `recursion_limit` of
  25 to bound worst-case cost/latency on a single request.
- Web search requires a Brave Search API key; without one, the tool
  degrades gracefully but obviously can't return live results.
