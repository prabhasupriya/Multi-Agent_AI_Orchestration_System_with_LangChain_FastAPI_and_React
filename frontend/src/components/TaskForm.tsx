import { useState } from "react";
import type { CreateTaskResponse } from "../types";

const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:8000";

interface Props {
  onTaskStarted: (taskId: string) => void;
  disabled: boolean;
}

const EXAMPLE_PROMPTS = [
  "What is the current weather in Tokyo, and based on that, what should I pack?",
  "Search for the latest news on renewable energy and summarize the key trend.",
  "If a trip costs $1240 split evenly between 4 people, how much does each person owe, and what's the weather like in Paris this week?",
];

export function TaskForm({ onTaskStarted, disabled }: Props) {
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (value: string) => {
    if (!value.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: value }),
      });
      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }
      const data: CreateTaskResponse = await response.json();
      onTaskStarted(data.task_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start task");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="task-form">
      <textarea
        className="task-form__textarea"
        placeholder="Ask something complex, e.g. 'What's the weather in Tokyo and what should I pack?'"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={4}
        disabled={disabled || submitting}
      />
      <div className="task-form__actions">
        <button
          className="task-form__submit"
          onClick={() => submit(prompt)}
          disabled={disabled || submitting || !prompt.trim()}
        >
          {submitting ? "Starting workflow..." : "Start Workflow"}
        </button>
      </div>

      {error && <p className="task-form__error">⚠ {error}</p>}

      <div className="task-form__examples">
        <span>Try an example:</span>
        {EXAMPLE_PROMPTS.map((example) => (
          <button
            key={example}
            className="task-form__example-chip"
            onClick={() => {
              setPrompt(example);
              submit(example);
            }}
            disabled={disabled || submitting}
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
