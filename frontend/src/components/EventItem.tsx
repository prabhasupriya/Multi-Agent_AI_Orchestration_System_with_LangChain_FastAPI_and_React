import type { AgentEvent } from "../types";

const AGENT_STYLES: Record<string, { color: string; icon: string }> = {
  Planner: { color: "#7c3aed", icon: "🧭" },
  Researcher: { color: "#2563eb", icon: "🔍" },
  Synthesizer: { color: "#059669", icon: "✍️" },
  System: { color: "#6b7280", icon: "⚙️" },
};

function describeEvent(event: AgentEvent): string {
  const payload = event.payload || {};
  switch (event.event_type) {
    case "AGENT_THOUGHT":
      return String(payload.message ?? "");
    case "TOOL_INVOCATION":
      return `Calling tool "${payload.tool}" with ${JSON.stringify(payload.arguments)}`;
    case "TOOL_RESULT":
      return String(payload.result ?? "");
    case "ERROR":
      return `Error: ${payload.message ?? "unknown error"}`;
    case "FINAL_RESULT":
      return "Final answer ready.";
    case "STATUS_CHANGE":
      return `Status changed to ${payload.status}`;
    default:
      return JSON.stringify(payload);
  }
}

export function EventItem({ event }: { event: AgentEvent }) {
  const agent = event.agent || "System";
  const style = AGENT_STYLES[agent] || AGENT_STYLES.System;
  const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : "";

  return (
    <div className="event-item" style={{ borderLeftColor: style.color }}>
      <div className="event-item__header">
        <span className="event-item__icon">{style.icon}</span>
        <span className="event-item__agent" style={{ color: style.color }}>
          {agent}
        </span>
        <span className="event-item__type">{event.event_type}</span>
        <span className="event-item__time">{time}</span>
      </div>
      <div className="event-item__body">{describeEvent(event)}</div>
    </div>
  );
}
