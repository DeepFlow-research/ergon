import type { ContextEventPayload } from "@/lib/contracts/contextEvents";
import { ContextEventCard, formatDuration } from "./ContextEventCard";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "thinking" }>;
  startedAt: string | null;
  completedAt: string | null;
}

export function ThinkingEvent({ payload, startedAt, completedAt }: Props) {
  return (
    <ContextEventCard
      tone="purple"
      title="Thinking"
      subtitle={payload.turn_id}
      duration={formatDuration(startedAt, completedAt)}
    >
      <p className="whitespace-pre-wrap italic text-purple-700">{payload.text}</p>
    </ContextEventCard>
  );
}
