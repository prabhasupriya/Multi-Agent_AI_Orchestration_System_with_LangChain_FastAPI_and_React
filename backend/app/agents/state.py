"""
Shared state passed between every node in the LangGraph state machine.

This is intentionally a plain TypedDict (rather than using LangGraph's
reducer/Annotated-list machinery) so the flow of data is easy to follow:
every node reads what it needs from the state and returns a dict of the
fields it wants to update; LangGraph merges those into the overall state.
"""
from typing import Any, TypedDict


class ResearchFinding(TypedDict):
    step: str
    tool: str
    result: str


class AgentState(TypedDict, total=False):
    task_id: str
    prompt: str
    plan: list[str]
    step_index: int
    research_results: list[ResearchFinding]
    final_result: str
    error: str
