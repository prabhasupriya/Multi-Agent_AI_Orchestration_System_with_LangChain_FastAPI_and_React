"""
Thin async repository layer around SQLAlchemy so that agent/graph code
never has to know about ORM/session details directly.
"""
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentEvent, EventType, TaskRun, TaskStatus


async def create_task_run(db: AsyncSession, task_id: str, prompt: str) -> TaskRun:
    task_run = TaskRun(id=task_id, prompt=prompt, status=TaskStatus.PENDING)
    db.add(task_run)
    await db.commit()
    await db.refresh(task_run)
    return task_run


async def update_task_status(
    db: AsyncSession, task_id: str, status: TaskStatus, final_result: Optional[str] = None
) -> None:
    result = await db.execute(select(TaskRun).where(TaskRun.id == task_id))
    task_run = result.scalar_one_or_none()
    if task_run is None:
        return
    task_run.status = status
    if final_result is not None:
        task_run.final_result = final_result
    await db.commit()


async def log_event(
    db: AsyncSession,
    task_id: str,
    agent_name: str,
    event_type: EventType,
    payload: dict[str, Any],
) -> AgentEvent:
    event = AgentEvent(
        task_run_id=task_id,
        agent_name=agent_name,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_task_run(db: AsyncSession, task_id: str) -> Optional[TaskRun]:
    result = await db.execute(select(TaskRun).where(TaskRun.id == task_id))
    return result.scalar_one_or_none()


async def get_events_for_task(db: AsyncSession, task_id: str) -> list[AgentEvent]:
    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.task_run_id == task_id)
        .order_by(AgentEvent.timestamp.asc())
    )
    return list(result.scalars().all())
