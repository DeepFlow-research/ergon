import type { ContextEventPayload, TokenLogprob } from "@/lib/contracts/contextEvents";
import type { ContextEventState } from "@/lib/types";

type ContextPartChunk = {
  part: Record<string, unknown>;
  token_ids?: number[] | null;
  logprobs?: TokenLogprob[] | null;
  sequence: number;
  worker_binding_key: string;
  turn_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  policy_version?: string | null;
};

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

export function contextPartToUiPayload(payload: unknown): ContextEventPayload {
  const record = asRecord(payload);
  if (typeof record.event_type === "string") {
    return payload as ContextEventPayload;
  }

  const part = asRecord(record.part);
  const eventType = part.part_kind;
  const tokenIds = (record.token_ids as number[] | null | undefined) ?? null;
  const logprobs = (record.logprobs as TokenLogprob[] | null | undefined) ?? null;
  const turnId = String(record.turn_id ?? "");

  switch (eventType) {
    case "system_prompt":
      return { event_type: "system_prompt", text: String(part.content ?? "") };
    case "user_message":
      return {
        event_type: "user_message",
        text: String(part.content ?? ""),
        from_worker_key: null,
      };
    case "assistant_text":
      return {
        event_type: "assistant_text",
        text: String(part.content ?? ""),
        turn_id: turnId,
        turn_token_ids: tokenIds,
        turn_logprobs: logprobs as Extract<
          ContextEventState["payload"],
          { event_type: "assistant_text" }
        >["turn_logprobs"],
      };
    case "tool_call":
      return {
        event_type: "tool_call",
        tool_call_id: String(part.tool_call_id ?? ""),
        tool_name: String(part.tool_name ?? ""),
        args: asRecord(part.args),
        turn_id: turnId,
        turn_token_ids: tokenIds,
        turn_logprobs: logprobs as Extract<
          ContextEventState["payload"],
          { event_type: "tool_call" }
        >["turn_logprobs"],
      };
    case "tool_result":
      return {
        event_type: "tool_result",
        tool_call_id: String(part.tool_call_id ?? ""),
        tool_name: String(part.tool_name ?? ""),
        result: part.content ?? null,
        is_error: Boolean(part.is_error ?? false),
      };
    case "thinking":
      return {
        event_type: "thinking",
        text: String(part.content ?? ""),
        turn_id: turnId,
        turn_token_ids: tokenIds,
        turn_logprobs: logprobs as Extract<
          ContextEventState["payload"],
          { event_type: "thinking" }
        >["turn_logprobs"],
      };
    default:
      throw new Error(`Unsupported context part kind: ${String(part.part_kind)}`);
  }
}

export const normalizeContextEventPayload = contextPartToUiPayload;

export function compareContextEvents(a: ContextEventState, b: ContextEventState): number {
  const at = Date.parse(a.createdAt);
  const bt = Date.parse(b.createdAt);
  if (Number.isFinite(at) && Number.isFinite(bt) && at !== bt) {
    return at - bt;
  }
  if (a.taskExecutionId !== b.taskExecutionId) {
    return a.taskExecutionId.localeCompare(b.taskExecutionId);
  }
  return a.sequence - b.sequence;
}

function stringifyContextResult(result: unknown): string {
  if (typeof result === "string") {
    return result;
  }
  return JSON.stringify(result) ?? "";
}

export function uiPayloadToContextPart(
  payload: ContextEventPayload,
  meta: {
    sequence: number;
    workerBindingKey: string;
    startedAt: string | null;
    completedAt: string | null;
  },
): ContextPartChunk {
  let part: Record<string, unknown>;

  switch (payload.event_type) {
    case "system_prompt":
      part = { part_kind: "system_prompt", content: payload.text };
      break;
    case "user_message":
      part = { part_kind: "user_message", content: payload.text };
      break;
    case "assistant_text":
      part = { part_kind: "assistant_text", content: payload.text };
      break;
    case "tool_call":
      part = {
        part_kind: "tool_call",
        tool_call_id: payload.tool_call_id,
        tool_name: payload.tool_name,
        args: payload.args,
      };
      break;
    case "tool_result":
      part = {
        part_kind: "tool_result",
        tool_call_id: payload.tool_call_id,
        tool_name: payload.tool_name,
        content: stringifyContextResult(payload.result),
        is_error: payload.is_error,
      };
      break;
    case "thinking":
      part = { part_kind: "thinking", content: payload.text };
      break;
  }

  const turnPayload = payload as {
    turn_id?: string | null;
    turn_token_ids?: number[] | null;
    turn_logprobs?: TokenLogprob[] | null;
  };

  return {
    part,
    token_ids: turnPayload.turn_token_ids ?? null,
    logprobs: turnPayload.turn_logprobs ?? null,
    sequence: meta.sequence,
    worker_binding_key: meta.workerBindingKey,
    turn_id: turnPayload.turn_id ?? null,
    started_at: meta.startedAt,
    completed_at: meta.completedAt,
    policy_version: null,
  };
}

export function serializeContextEvent(event: ContextEventState): ContextEventState {
  return {
    ...event,
    payload: uiPayloadToContextPart(event.payload, {
      sequence: event.sequence,
      workerBindingKey: event.workerBindingKey,
      startedAt: event.startedAt,
      completedAt: event.completedAt,
    }) as unknown as ContextEventState["payload"],
  };
}
