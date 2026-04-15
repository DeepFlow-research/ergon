import type { ContextEventState } from "@/lib/contracts/contextEvents";
import { AssistantTextEvent } from "./events/AssistantTextEvent";
import { SystemPromptEvent } from "./events/SystemPromptEvent";
import { ThinkingEvent } from "./events/ThinkingEvent";
import { ToolCallEvent } from "./events/ToolCallEvent";
import { ToolResultEvent } from "./events/ToolResultEvent";
import { UserMessageEvent } from "./events/UserMessageEvent";

interface Props {
  event: ContextEventState;
}

export function ContextEventEntry({ event }: Props) {
  switch (event.eventType) {
    case "system_prompt":
      return (
        <SystemPromptEvent
          payload={
            event.payload as Extract<typeof event.payload, { event_type: "system_prompt" }>
          }
        />
      );
    case "user_message":
      return (
        <UserMessageEvent
          payload={
            event.payload as Extract<typeof event.payload, { event_type: "user_message" }>
          }
        />
      );
    case "thinking":
      return (
        <ThinkingEvent
          payload={event.payload as Extract<typeof event.payload, { event_type: "thinking" }>}
          startedAt={event.startedAt}
          completedAt={event.completedAt}
        />
      );
    case "assistant_text":
      return (
        <AssistantTextEvent
          payload={
            event.payload as Extract<typeof event.payload, { event_type: "assistant_text" }>
          }
          startedAt={event.startedAt}
          completedAt={event.completedAt}
        />
      );
    case "tool_call":
      return (
        <ToolCallEvent
          payload={event.payload as Extract<typeof event.payload, { event_type: "tool_call" }>}
          startedAt={event.startedAt}
          completedAt={event.completedAt}
        />
      );
    case "tool_result":
      return (
        <ToolResultEvent
          payload={
            event.payload as Extract<typeof event.payload, { event_type: "tool_result" }>
          }
        />
      );
    default: {
      const _exhaustive: never = event.eventType;
      return <p className="text-xs text-red-400">Unknown event: {String(_exhaustive)}</p>;
    }
  }
}
