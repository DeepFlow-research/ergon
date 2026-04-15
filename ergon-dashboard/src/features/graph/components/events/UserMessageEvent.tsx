import type { ContextEventPayload } from "@/lib/contracts/contextEvents";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "user_message" }>;
}

export function UserMessageEvent({ payload }: Props) {
  return (
    <div className="rounded bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
      {payload.from_worker_key && (
        <span className="mb-1 block text-xs text-indigo-400">
          from {payload.from_worker_key}
        </span>
      )}
      <p>{payload.text}</p>
    </div>
  );
}
