import type { ContextEventPayload } from "@/lib/contracts/contextEvents";
import { ContextEventCard } from "./ContextEventCard";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "user_message" }>;
}

export function UserMessageEvent({ payload }: Props) {
  return (
    <ContextEventCard
      tone="indigo"
      title="User message"
      badge={payload.from_worker_key ? `from ${payload.from_worker_key}` : null}
    >
      <p>{payload.text}</p>
    </ContextEventCard>
  );
}
