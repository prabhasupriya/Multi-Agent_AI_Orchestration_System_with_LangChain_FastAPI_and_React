import { useEffect, useRef, useState } from "react";
import type { AgentEvent } from "../types";

const WS_BASE_URL =
  (import.meta as any).env?.VITE_WS_BASE_URL || "ws://localhost:8000";

/**
 * Connects to /api/ws/{taskId} as soon as a taskId is provided, appends
 * every incoming event to state, and exposes the live connection status.
 * The connection is closed automatically when the component unmounts or
 * the taskId changes.
 */
export function useAgentWebSocket(taskId: string | null) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) return;

    setEvents([]);
    setIsComplete(false);

    const socket = new WebSocket(`${WS_BASE_URL}/api/ws/${taskId}`);
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);

    socket.onmessage = (event) => {
      try {
        const data: AgentEvent = JSON.parse(event.data);
        if (data.event_type === "PING") return; // heartbeat, ignore
        setEvents((prev) => [...prev, data]);
        if (
          data.event_type === "STATUS_CHANGE" &&
          (data.payload?.status === "COMPLETED" || data.payload?.status === "FAILED")
        ) {
          setIsComplete(true);
        }
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [taskId]);

  return { events, connected, isComplete };
}
