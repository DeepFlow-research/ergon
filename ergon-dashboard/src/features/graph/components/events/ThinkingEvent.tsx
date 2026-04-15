import type { ContextEventPayload } from "@/lib/contracts/contextEvents";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "thinking" }>;
  startedAt: string | null;
  completedAt: string | null;
}

export function ThinkingEvent({ payload, startedAt, completedAt }: Props) {
  return (
    <details className="rounded border border-purple-200 bg-purple-50 p-2 text-xs">
      <summary className="cursor-pointer font-medium text-purple-700">
        Thinking
        {startedAt && completedAt && (
          <span className="ml-2 text-purple-400">
            {Math.round(
              (new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 100,
            ) / 10}
            s
          </span>
        )}
      </summary>
      <p className="mt-1 italic text-purple-600">{payload.text}</p>
    </details>
  );
}
