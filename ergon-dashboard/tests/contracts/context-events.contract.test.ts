import assert from "node:assert/strict";
import test from "node:test";

import {
  contextPartToUiPayload,
  uiPayloadToContextPart,
} from "../../src/lib/run-state/contextEvents";

test("tool_call context part converts to UI payload", () => {
  const payload = contextPartToUiPayload({
    part: {
      part_kind: "tool_call",
      tool_call_id: "call-1",
      tool_name: "lean_check",
      args: { file: "proof.lean" },
    },
    token_ids: [1, 2],
    logprobs: null,
    sequence: 0,
    worker_binding_key: "react-worker",
    turn_id: "turn-1",
    started_at: "2026-03-18T12:00:00.000Z",
    completed_at: "2026-03-18T12:00:01.000Z",
    policy_version: null,
  });

  assert.deepEqual(payload, {
    event_type: "tool_call",
    tool_call_id: "call-1",
    tool_name: "lean_check",
    args: { file: "proof.lean" },
    turn_id: "turn-1",
    turn_token_ids: [1, 2],
    turn_logprobs: null,
  });
});

test("UI tool_result payload serializes to context part", () => {
  const payload = uiPayloadToContextPart(
    {
      event_type: "tool_result",
      tool_call_id: "call-1",
      tool_name: "lean_check",
      result: "ok",
      is_error: false,
    },
    {
      sequence: 3,
      workerBindingKey: "react-worker",
      startedAt: null,
      completedAt: null,
    },
  );

  assert.equal(payload.part.part_kind, "tool_result");
  assert.equal(payload.part.tool_name, "lean_check");
  assert.equal(payload.sequence, 3);
});
