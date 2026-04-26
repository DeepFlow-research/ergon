import type { ContextEventPayload } from "@/lib/contracts/contextEvents";
import { ContextEventCard, formatDuration } from "./ContextEventCard";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "tool_call" }>;
  startedAt: string | null;
  completedAt: string | null;
}

export function ToolCallEvent({ payload, startedAt, completedAt }: Props) {
  return (
    <ContextEventCard
      tone="blue"
      title="Tool call"
      badge={payload.tool_name}
      subtitle={payload.tool_call_id}
      duration={formatDuration(startedAt, completedAt)}
      payloadLabel="Arguments"
      payload={payload.args}
    />
  );
}
