import type { AgentEvent } from "../types";

interface Props {
  events: AgentEvent[];
}

export function FinalResult({ events }: Props) {
  const finalEvent = [...events].reverse().find((e) => e.event_type === "FINAL_RESULT");
  if (!finalEvent) return null;

  const text = String(finalEvent.payload?.message ?? "");

  return (
    <div className="final-result">
      <h3>✅ Final Answer</h3>
      <p>{text}</p>
    </div>
  );
}
