"""
Relational schema for full auditability of every agentic workflow.

TaskRun   -> one row per user-submitted prompt / workflow execution.
AgentEvent -> one row per discrete thing that happened during that run
              (an agent's thought, a tool invocation, a tool result, an
              error, or a status transition). This is what lets us
              reconstruct exactly what happened, and why, after the fact.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EventType(str, enum.Enum):
    STATUS_CHANGE = "STATUS_CHANGE"
    AGENT_THOUGHT = "AGENT_THOUGHT"
    TOOL_INVOCATION = "TOOL_INVOCATION"
    TOOL_RESULT = "TOOL_RESULT"
    ERROR = "ERROR"
    FINAL_RESULT = "FINAL_RESULT"


class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt = Column(Text, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    final_result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events = relationship(
        "AgentEvent", back_populates="task_run", cascade="all, delete-orphan"
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_run_id = Column(String, ForeignKey("task_runs.id"), nullable=False, index=True)
    agent_name = Column(String, nullable=False)  # e.g. 'Planner', 'Researcher', 'Synthesizer'
    event_type = Column(Enum(EventType), nullable=False)
    payload = Column(JSON, nullable=False)  # arbitrary structured data for this event
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    task_run = relationship("TaskRun", back_populates="events")
