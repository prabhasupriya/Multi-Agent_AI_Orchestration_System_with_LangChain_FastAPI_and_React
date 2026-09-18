import { useEffect, useRef } from "react";
import type { AgentEvent } from "../types";
import { EventItem } from "./EventItem";

interface Props {
  events: AgentEvent[];
  connected: boolean;
}

export function Timeline({ events, connected }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="timeline timeline--empty">
        <p>No activity yet. Submit a prompt above to watch the agents work.</p>
      </div>
    );
  }

  return (
    <div className="timeline">
      <div className="timeline__status">
        <span className={`status-dot ${connected ? "status-dot--live" : ""}`} />
        {connected ? "Live" : "Disconnected"}
      </div>
      <div className="timeline__list">
        {events.map((event, idx) => (
          <EventItem key={idx} event={event} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
