# Multi-Agent Orchestration System

A stateful, multi-agent AI system that plans, researches, and synthesizes
answers to complex prompts — with every step streamed live to the browser
and permanently logged for auditability.

Three specialized agents (**Planner → Researcher → Synthesizer**) collaborate
through a [LangGraph](https://github.com/langchain-ai/langgraph) state
machine. The Researcher calls out to three custom tools (web search, weather,
calculation), which are executed on **Celery** workers backed by **Redis** so
slow third-party API calls never block the API server. Every agent thought,
tool call, and result is persisted to **PostgreSQL** and pushed to the
**React** frontend over a **WebSocket**, giving the user a live trace of the
system "thinking."

```
User prompt
   │
   ▼
┌─────────┐     ┌────────────┐     ┌─────────────┐
│ Planner │ ──▶ │ Researcher │ ──▶ │ Synthesizer │ ──▶ Final answer
└─────────┘     └─────┬──────┘     └─────────────┘
                      │  (loops once per plan step)
                      ▼
            ┌───────────────────┐
            │  Celery + Redis    │
            │  web_search        │
            │  weather_lookup    │
            │  calculation       │
            └───────────────────┘

Every transition → logged to Postgres + published to Redis pub/sub
                                   │
                                   ▼
                     WebSocket → React live timeline
```

## Features

- **Three specialized agents** with distinct system prompts and
  responsibilities (Planner, Researcher, Synthesizer).
- **Three custom tools** (`web_search`, `weather_lookup`, `calculation`),
  each with a strict Pydantic input schema and defensive error handling —
  a failing tool returns a descriptive error string instead of crashing
  the process, so the agent can adapt.
- **Asynchronous, non-blocking architecture**: tool execution is offloaded
  to Celery workers; the FastAPI event loop is only ever `await`-ing, never
  blocking, so WebSocket connections stay responsive during long tool runs.
- **Full auditability**: every agent thought, tool invocation, tool result,
  and status transition is written to Postgres (`task_runs` +
  `agent_events`) as it happens.
- **Real-time visualization**: a React timeline UI shows the agents working,
  color-coded by role, with a live connection indicator and the final
  synthesized answer highlighted at the end.
- **One-command startup**: `docker compose up --build` brings up all five
  services (API, UI, Postgres, Redis, Celery worker) with health-checked
  startup ordering.

## Example complex tasks the system can handle

- *"What is the current weather in Tokyo, and based on that, what should I
  pack?"* — Planner splits this into a weather-lookup step and a reasoning
  step; Researcher calls `weather_lookup`; Synthesizer turns the raw
  conditions into packing advice.
- *"If a trip costs $1240 split evenly between 4 people, how much does each
  person owe, and what's the weather like in Paris this week?"* — exercises
  both the `calculation` and `weather_lookup` tools in the same run.
- *"Search for the latest news on renewable energy and summarize the key
  trend."* — exercises `web_search` and pure synthesis.

## Architecture

See [EVALUATION.md](./EVALUATION.md) for the full design rationale
(orchestration pattern, agent roles/prompts, tool schemas, and error
handling strategy).

| Layer            | Technology                                   |
|-------------------|-----------------------------------------------|
| API               | FastAPI (async), Uvicorn                      |
| Orchestration     | LangGraph (LangChain)                         |
| LLM               | OpenAI or Anthropic (swap via env var)        |
| Async tool queue  | Celery + Redis                                |
| Real-time channel | WebSockets + Redis pub/sub                    |
| Persistence       | PostgreSQL + SQLAlchemy (async, asyncpg)      |
| Frontend          | React 18 + TypeScript + Vite                  |
| Orchestration     | Docker Compose (5 services, health-checked)   |

## Project structure

```
project-root/
├── backend/
│   ├── app/
│   │   ├── api/          # REST (tasks.py) + WebSocket (ws.py) endpoints
│   │   ├── core/         # config, Celery app
│   │   ├── db/           # SQLAlchemy models, async engine, repository
│   │   ├── agents/       # LangGraph state, prompts, graph, runner
│   │   ├── tools/        # Pydantic schemas + tool implementation logic
│   │   ├── worker/       # Celery task wrappers around the tools
│   │   └── main.py       # FastAPI app entrypoint
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   # TaskForm, Timeline, EventItem, FinalResult
│   │   ├── hooks/        # useAgentWebSocket
│   │   └── App.tsx
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── .env.example
├── README.md
└── EVALUATION.md
```

## Getting started

### Prerequisites

- Docker + Docker Compose
- An OpenAI or Anthropic API key (for the LLM)
- (Optional, for full tool functionality) an OpenWeatherMap API key and a
  Brave Search API key — the app runs fine without them, but those two
  tools will return a graceful "not configured" error until you add keys.

### 1. Configure environment variables

```bash
cp .env.example .env
# then edit .env and fill in LLM_API_KEY at minimum
```

### 2. Start everything

```bash
docker compose up --build
```

This starts, in dependency order (with health checks):

1. `db` — Postgres 15
2. `redis` — Redis 7
3. `api` — FastAPI on **http://localhost:8000**
4. `worker` — Celery worker consuming tool tasks
5. `ui` — React app on **http://localhost:3000**

### 3. Use it

Open **http://localhost:3000**, type a prompt (or click one of the example
chips), and watch the timeline populate in real time as the Planner,
Researcher, and Synthesizer agents work.

### Verifying each service manually

```bash
# API health
curl http://localhost:8000/health

# Kick off a task via curl
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the weather in Tokyo and what should I pack?"}'
# → {"task_id": "..."}

# Check task status
curl http://localhost:8000/api/tasks/<task_id>

# Watch Celery pick up tool tasks
docker compose logs worker -f

# Inspect the audit trail directly in Postgres
docker compose exec db psql -U agent_user -d agent_db \
  -c "SELECT agent_name, event_type, timestamp FROM agent_events ORDER BY timestamp;"
```

A WebSocket client (e.g. `websocat ws://localhost:8000/api/ws/<task_id>`)
will show the same event stream the React UI consumes.

## Local development (without Docker)

<details>
<summary>Backend</summary>

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(cat ../.env | xargs)   # or use python-dotenv
uvicorn app.main:app --reload

# In a second terminal, run the Celery worker:
celery -A app.core.celery_app.celery_app worker --loglevel=info
```

You'll still need Postgres and Redis running locally (or point
`DATABASE_URL`/`REDIS_URL` at Dockerized instances).
</details>

<details>
<summary>Frontend</summary>

```bash
cd frontend
npm install
npm run dev
```
</details>

## Testing tool failure handling

Leave `OPENWEATHER_API_KEY` blank in `.env` and ask a weather-related
question. The `weather_lookup` tool will catch the missing-key condition
internally and return an error string (visible in the timeline as a
`TOOL_RESULT` event) instead of crashing — the Synthesizer will then
acknowledge the limitation in its final answer rather than inventing data.

## Notes on the LLM provider

The `.env.example` defaults to **Groq** (`LLM_PROVIDER=groq`,
`openai/gpt-oss-20b`) since it's fast and has a generous free tier —
grab a key at [console.groq.com/keys](https://console.groq.com/keys) and
drop it into `LLM_API_KEY`.

To use OpenAI or Anthropic instead, just change two lines in `.env`:

```dotenv
# OpenAI
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Anthropic
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-latest
```

No code changes are needed for any of these — every agent (Planner,
Researcher, Synthesizer) calls the single `get_llm()` factory in
`app/agents/llm.py`, which reads `LLM_PROVIDER` and returns the right
client.

## youtude video 
[click link](https://youtu.be/Ej63dwTWK14?si=6hKyoBUyOH7yvBoq)
