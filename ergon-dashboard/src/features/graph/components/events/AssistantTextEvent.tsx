import type { ContextEventPayload } from "@/lib/contracts/contextEvents";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "assistant_text" }>;
  startedAt: string | null;
  completedAt: string | null;
}

export function AssistantTextEvent({ payload, startedAt, completedAt }: Props) {
  return (
    <div className="rounded bg-white px-3 py-2 text-sm shadow-sm ring-1 ring-gray-200">
      {startedAt && completedAt && (
        <span className="mb-1 block text-xs text-gray-400">
          {Math.round(
            (new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 100,
          ) / 10}
          s
        </span>
      )}
      <p className="whitespace-pre-wrap">{payload.text}</p>
    </div>
  );
}
