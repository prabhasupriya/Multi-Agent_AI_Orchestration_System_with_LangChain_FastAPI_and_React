"""
Glue code that runs a compiled agent graph for one task, persisting every
event to Postgres AND publishing it to a Redis pub/sub channel so any
FastAPI worker process holding the relevant WebSocket connection can relay
it to the browser in real time.
"""
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis

from app.agents.graph import build_agent_graph
from app.core.config import get_settings
from app.db.database import AsyncSessionLocal
from app.db.models import EventType, TaskStatus
from app.db.repository import log_event, update_task_status

logger = logging.getLogger(__name__)
settings = get_settings()


def channel_name(task_id: str) -> str:
    return f"ws:{task_id}"


async def run_agent_workflow(task_id: str, prompt: str) -> None:
    """Entry point invoked as a background asyncio task by the REST API
    right after a TaskRun row is created."""
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def emit(agent_name: str, event_type: EventType, payload: dict) -> None:
        """Persist the event to Postgres and publish it to Redis so any
        connected WebSocket client sees it immediately."""
        async with AsyncSessionLocal() as db:
            await log_event(db, task_id, agent_name, event_type, payload)

        message = {
            "task_id": task_id,
            "event_type": event_type.value,
            "agent": agent_name,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await redis_client.publish(channel_name(task_id), json.dumps(message))

    try:
        async with AsyncSessionLocal() as db:
            await update_task_status(db, task_id, TaskStatus.IN_PROGRESS)
        await emit("System", EventType.STATUS_CHANGE, {"status": "IN_PROGRESS"})

        app_graph = build_agent_graph(emit)
        final_state = await app_graph.ainvoke(
            {"task_id": task_id, "prompt": prompt},
            config={"recursion_limit": 25},
        )

        async with AsyncSessionLocal() as db:
            await update_task_status(
                db, task_id, TaskStatus.COMPLETED, final_result=final_state.get("final_result")
            )
        await emit(
            "System",
            EventType.STATUS_CHANGE,
            {"status": "COMPLETED", "final_result": final_state.get("final_result")},
        )
    except Exception as exc:  # noqa: BLE001 - top-level safety net for the whole workflow
        logger.exception("Agent workflow failed for task %s", task_id)
        async with AsyncSessionLocal() as db:
            await update_task_status(db, task_id, TaskStatus.FAILED, final_result=str(exc))
        await emit("System", EventType.ERROR, {"message": str(exc)})
        await emit("System", EventType.STATUS_CHANGE, {"status": "FAILED"})
    finally:
        await redis_client.aclose()
