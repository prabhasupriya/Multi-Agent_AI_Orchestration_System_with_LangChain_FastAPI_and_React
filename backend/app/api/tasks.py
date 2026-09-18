"""
POST /api/tasks - kick off a new multi-agent workflow.

The endpoint itself only creates the TaskRun row and schedules the actual
(potentially long-running) agent workflow as a background asyncio task,
then returns immediately with the task_id. The client is expected to open
a WebSocket to /api/ws/{task_id} right after to watch it run.
"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import run_agent_workflow
from app.db.database import get_db
from app.db.models import TaskStatus
from app.db.repository import create_task_run, get_task_run

router = APIRouter(prefix="/api", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class CreateTaskResponse(BaseModel):
    task_id: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    prompt: str
    final_result: str | None = None


@router.post("/tasks", response_model=CreateTaskResponse, status_code=201)
async def create_task(
    request: CreateTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    task_id = str(uuid.uuid4())
    await create_task_run(db, task_id=task_id, prompt=request.prompt)

    # Runs after the HTTP response is sent, without blocking the client.
    background_tasks.add_task(run_agent_workflow, task_id, request.prompt)

    return CreateTaskResponse(task_id=task_id)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task_run = await get_task_run(db, task_id)
    if task_run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(
        task_id=task_run.id,
        status=task_run.status,
        prompt=task_run.prompt,
        final_result=task_run.final_result,
    )
