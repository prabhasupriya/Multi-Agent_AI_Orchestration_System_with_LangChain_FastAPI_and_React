"""
WS /api/ws/{task_id} - real-time streaming of agent events.

On connect we:
  1. Replay any events already logged for this task (handles the client
     connecting slightly after the workflow started).
  2. Subscribe to the task's Redis pub/sub channel and forward every new
     event as it's published by the running workflow (which may be
     executing in a different process).
  3. Send periodic pings so reverse proxies / browsers don't kill an
     idle-looking connection during a long-running tool call.
"""
import asyncio
import json
import logging

import redis.asyncio as redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.runner import channel_name
from app.core.config import get_settings
from app.db.database import AsyncSessionLocal
from app.db.repository import get_events_for_task

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

HEARTBEAT_INTERVAL_SECONDS = 20


@router.websocket("/api/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()

    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()

    try:
        # 1. Replay history so late-connecting clients aren't missing anything.
        async with AsyncSessionLocal() as db:
            past_events = await get_events_for_task(db, task_id)
        for event in past_events:
            await websocket.send_json(
                {
                    "task_id": task_id,
                    "event_type": event.event_type.value,
                    "agent": event.agent_name,
                    "payload": event.payload,
                    "timestamp": event.timestamp.isoformat(),
                }
            )

        # 2. Subscribe for live updates.
        await pubsub.subscribe(channel_name(task_id))

        listen_task = asyncio.create_task(_relay_pubsub(pubsub, websocket))
        heartbeat_task = asyncio.create_task(_heartbeat(websocket))

        # 3. Also watch for the client disconnecting.
        try:
            while True:
                # We don't expect inbound messages, but reading lets us
                # detect a disconnect promptly.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            listen_task.cancel()
            heartbeat_task.cancel()
    except Exception:  # noqa: BLE001
        logger.exception("WebSocket error for task %s", task_id)
    finally:
        await pubsub.unsubscribe(channel_name(task_id))
        await pubsub.aclose()
        await redis_client.aclose()


async def _relay_pubsub(pubsub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            await websocket.send_json(data)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to relay pubsub message")


async def _heartbeat(websocket: WebSocket) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        try:
            await websocket.send_json({"event_type": "PING"})
        except Exception:  # noqa: BLE001
            break
