import type { ContextEventPayload } from "@/lib/contracts/contextEvents";
import { ContextEventCard } from "./ContextEventCard";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "system_prompt" }>;
}

export function SystemPromptEvent({ payload }: Props) {
  return (
    <ContextEventCard
      tone="gray"
      title="System prompt"
      payloadLabel="Prompt"
      payload={payload.text}
    />
  );
}
