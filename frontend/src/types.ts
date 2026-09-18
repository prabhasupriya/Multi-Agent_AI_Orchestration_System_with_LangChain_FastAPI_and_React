export type EventType =
  | "STATUS_CHANGE"
  | "AGENT_THOUGHT"
  | "TOOL_INVOCATION"
  | "TOOL_RESULT"
  | "ERROR"
  | "FINAL_RESULT"
  | "PING";

export interface AgentEvent {
  task_id?: string;
  event_type: EventType;
  agent?: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

export interface CreateTaskResponse {
  task_id: string;
}
