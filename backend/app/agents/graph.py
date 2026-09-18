"""
The core multi-agent orchestration graph, built with LangGraph.

Three specialized agents collaborate via a shared `AgentState`:

    Planner ---> Researcher (loops once per plan step) ---> Synthesizer

Each node is a thin async function that:
  1. does its reasoning/tool work,
  2. emits an audit event (persisted to Postgres + streamed over the
     WebSocket) via the `emit` callback it was built with,
  3. returns a partial state update.

Tool execution is delegated to Celery (see app/worker/tasks.py) so a slow
third-party API call never blocks this event loop.
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable

from langgraph.graph import END, StateGraph

from app.agents.llm import get_llm
from app.agents.prompts import (
    PLANNER_SYSTEM_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    SYNTHESIZER_SYSTEM_PROMPT,
)
from app.agents.state import AgentState
from app.core.config import get_settings
from app.db.models import EventType
from app.worker.tasks import calculation_task, weather_lookup_task, web_search_task

logger = logging.getLogger(__name__)
settings = get_settings()

# Callback signature: (agent_name, event_type, payload) -> awaitable
EmitFn = Callable[[str, EventType, dict], Awaitable[None]]

TOOL_DISPATCH = {
    "web_search": web_search_task,
    "weather_lookup": weather_lookup_task,
    "calculation": calculation_task,
}


def _extract_json(text: str) -> str:
    """LLMs occasionally wrap JSON in markdown fences despite instructions
    not to. Strip those defensively before parsing."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


async def _run_celery_tool(tool_name: str, arguments: dict) -> str:
    """Dispatch a tool call to Celery and asynchronously await the result
    without blocking the FastAPI event loop (the blocking `.get()` call
    runs in a worker thread via asyncio.to_thread)."""
    task_fn = TOOL_DISPATCH.get(tool_name)
    if task_fn is None:
        return f"Error: Unknown tool '{tool_name}' requested."

    async_result = task_fn.delay(**arguments)
    try:
        result = await asyncio.to_thread(
            async_result.get, timeout=settings.TOOL_RESULT_TIMEOUT_SECONDS
        )
        return str(result)
    except Exception as exc:  # noqa: BLE001
        return f"Error: Tool '{tool_name}' did not complete in time or failed ({exc})."


def build_agent_graph(emit: EmitFn):
    """Factory that builds a fresh compiled LangGraph app, closing over the
    `emit` callback used to stream/persist events for THIS task run."""

    llm = get_llm()

    # ---------------------------------------------------------------- Planner
    async def planner_node(state: AgentState) -> dict:
        await emit(
            "Planner", EventType.AGENT_THOUGHT, {"message": "Breaking the request into steps..."}
        )
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": state["prompt"]},
        ]
        try:
            response = await llm.ainvoke(messages)
            plan = json.loads(_extract_json(response.content))
            if not isinstance(plan, list) or not plan:
                raise ValueError("Planner did not return a non-empty JSON list")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Planner fallback triggered: %s", exc)
            plan = [state["prompt"]]  # graceful fallback: treat whole prompt as one step

        await emit("Planner", EventType.AGENT_THOUGHT, {"message": "Plan created.", "plan": plan})
        return {"plan": plan, "step_index": 0, "research_results": []}

    # -------------------------------------------------------------- Researcher
    async def researcher_node(state: AgentState) -> dict:
        idx = state.get("step_index", 0)
        step = state["plan"][idx]

        await emit(
            "Researcher",
            EventType.AGENT_THOUGHT,
            {"message": f"Working on step {idx + 1}/{len(state['plan'])}: {step}"},
        )

        decision_messages = [
            {"role": "system", "content": RESEARCHER_SYSTEM_PROMPT},
            {"role": "user", "content": step},
        ]
        tool_name = "none"
        arguments: dict = {}
        reasoning = ""
        try:
            decision_response = await llm.ainvoke(decision_messages)
            decision = json.loads(_extract_json(decision_response.content))
            tool_name = decision.get("tool", "none")
            arguments = decision.get("arguments", {}) or {}
            reasoning = decision.get("reasoning", "")
        except Exception as exc:  # noqa: BLE001
            reasoning = f"Could not parse tool decision ({exc}); proceeding without a tool."

        if tool_name in TOOL_DISPATCH:
            await emit(
                "Researcher",
                EventType.TOOL_INVOCATION,
                {"tool": tool_name, "arguments": arguments, "reasoning": reasoning},
            )
            result_text = await _run_celery_tool(tool_name, arguments)
            await emit(
                "Researcher",
                EventType.TOOL_RESULT,
                {"tool": tool_name, "result": result_text},
            )
        else:
            result_text = reasoning or "No tool was needed for this step."
            await emit(
                "Researcher",
                EventType.AGENT_THOUGHT,
                {"message": result_text},
            )

        findings = list(state.get("research_results", []))
        findings.append({"step": step, "tool": tool_name, "result": result_text})

        return {"research_results": findings, "step_index": idx + 1}

    def route_after_researcher(state: AgentState) -> str:
        if state.get("step_index", 0) < len(state.get("plan", [])):
            return "researcher"
        return "synthesizer"

    # ------------------------------------------------------------- Synthesizer
    async def synthesizer_node(state: AgentState) -> dict:
        await emit(
            "Synthesizer",
            EventType.AGENT_THOUGHT,
            {"message": "Synthesizing findings into a final answer..."},
        )
        findings_text = "\n".join(
            f"- Step: {f['step']}\n  Tool used: {f['tool']}\n  Result: {f['result']}"
            for f in state.get("research_results", [])
        )
        messages = [
            {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Original request: {state['prompt']}\n\nResearch findings:\n{findings_text}",
            },
        ]
        try:
            response = await llm.ainvoke(messages)
            final_text = response.content
        except Exception as exc:  # noqa: BLE001
            final_text = (
                "I was unable to fully synthesize a response due to an internal "
                f"error ({exc}). Here is the raw research gathered:\n{findings_text}"
            )

        await emit("Synthesizer", EventType.FINAL_RESULT, {"message": final_text})
        return {"final_result": final_text}

    # ------------------------------------------------------------------ Graph
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "researcher")
    graph.add_conditional_edges(
        "researcher",
        route_after_researcher,
        {"researcher": "researcher", "synthesizer": "synthesizer"},
    )
    graph.add_edge("synthesizer", END)

    return graph.compile()
