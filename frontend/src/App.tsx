import { useState } from "react";
import { TaskForm } from "./components/TaskForm";
import { Timeline } from "./components/Timeline";
import { FinalResult } from "./components/FinalResult";
import { useAgentWebSocket } from "./hooks/useAgentWebSocket";
import "./index.css";

export default function App() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const { events, connected, isComplete } = useAgentWebSocket(taskId);

  return (
    <div className="app">
      <header className="app__header">
        <h1>🤖 Multi-Agent Orchestration Console</h1>
        <p>Planner → Researcher → Synthesizer, streamed live via LangGraph + WebSockets.</p>
      </header>

      <TaskForm onTaskStarted={setTaskId} disabled={Boolean(taskId) && !isComplete} />

      {taskId && (
        <div className="app__task-id">
          Task ID: <code>{taskId}</code>
        </div>
      )}

      <Timeline events={events} connected={connected} />

      <FinalResult events={events} />
    </div>
  );
}
