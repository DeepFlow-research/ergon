import type { ContextEventPayload } from "@/lib/contracts/contextEvents";
import { ContextEventCard, formatDuration } from "./ContextEventCard";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "assistant_text" }>;
  startedAt: string | null;
  completedAt: string | null;
}

export function AssistantTextEvent({ payload, startedAt, completedAt }: Props) {
  return (
    <ContextEventCard
      tone="amber"
      title="Assistant"
      subtitle={payload.turn_id}
      duration={formatDuration(startedAt, completedAt)}
    >
      <p className="whitespace-pre-wrap">{payload.text}</p>
    </ContextEventCard>
  );
}
