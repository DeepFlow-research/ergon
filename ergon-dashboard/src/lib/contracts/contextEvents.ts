// ergon-dashboard/src/lib/contracts/contextEvents.ts
/**
 * TypeScript types for run_context_events — mirrors Python ContextEventPayload.
 * Must stay in sync with ergon_core/ergon_core/core/persistence/context/event_payloads.py
 */

export type ContextEventType =
  | "system_prompt"
  | "user_message"
  | "assistant_text"
  | "tool_call"
  | "tool_result"
  | "thinking";

export interface TokenLogprob {
  token: string;
  logprob: number;
}

export type ContextEventPayload =
  | { event_type: "system_prompt"; text: string }
  | { event_type: "user_message"; text: string; from_worker_key: string | null }
  | {
      event_type: "assistant_text";
      text: string;
      turn_id: string;
      turn_logprobs: TokenLogprob[] | null;
    }
  | {
      event_type: "tool_call";
      tool_call_id: string;
      tool_name: string;
      args: Record<string, unknown>;
      turn_id: string;
      turn_logprobs: TokenLogprob[] | null;
    }
  | {
      event_type: "tool_result";
      tool_call_id: string;
      tool_name: string;
      result: unknown;
      is_error: boolean;
    }
  | {
      event_type: "thinking";
      text: string;
      turn_id: string;
      turn_logprobs: TokenLogprob[] | null;
    };

export interface ContextEventState {
  id: string;
  taskExecutionId: string;
  taskNodeId: string;
  workerBindingKey: string;
  sequence: number;
  eventType: ContextEventType;
  payload: ContextEventPayload;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}
