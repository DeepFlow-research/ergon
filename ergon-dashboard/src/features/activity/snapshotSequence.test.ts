import assert from "node:assert/strict";
import test from "node:test";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import type { RunActivity } from "./types";
import { resolveActivitySnapshotSequence } from "./snapshotSequence";

function activity(overrides: Partial<RunActivity> = {}): RunActivity {
  return {
    id: "activity-1",
    kind: "execution",
    band: "work",
    label: "Activity",
    taskId: "task-1",
    sequence: null,
    startAt: "2026-04-26T12:00:10.000Z",
    endAt: null,
    isInstant: true,
    actor: null,
    sourceKind: "execution.span",
    metadata: {},
    lineage: { taskId: "task-1", taskExecutionId: "activity-1" },
    ...overrides,
    debug: overrides.debug ?? { source: "execution.span", payload: { id: "activity-1" } },
  };
}

function mutation(sequence: number, createdAt: string): GraphMutationDto {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    run_id: "00000000-0000-4000-8000-000000000002",
    sequence,
    mutation_type: "node.added",
    target_type: "node",
    target_id: "00000000-0000-4000-8000-000000000003",
    actor: "system",
    old_value: null,
    new_value: {},
    reason: null,
    created_at: createdAt,
  };
}

test("uses explicit activity sequence when present", () => {
  const result = resolveActivitySnapshotSequence(
    activity({ sequence: 7, startAt: "not-a-date" }),
    [mutation(1, "2026-04-26T12:00:00.000Z")],
  );

  assert.equal(result, 7);
});

test("uses nearest mutation at or before activity start time when sequence is absent", () => {
  const result = resolveActivitySnapshotSequence(
    activity({ startAt: "2026-04-26T12:00:10.000Z" }),
    [
      mutation(1, "2026-04-26T12:00:00.000Z"),
      mutation(2, "2026-04-26T12:00:05.000Z"),
      mutation(3, "2026-04-26T12:00:15.000Z"),
    ],
  );

  assert.equal(result, 2);
});

test("uses matching mutation timestamp and highest sequence for timestamp ties", () => {
  const result = resolveActivitySnapshotSequence(
    activity({ startAt: "2026-04-26T12:00:10.000Z" }),
    [
      mutation(1, "2026-04-26T12:00:00.000Z"),
      mutation(2, "2026-04-26T12:00:10.000Z"),
      mutation(3, "2026-04-26T12:00:10.000Z"),
    ],
  );

  assert.equal(result, 3);
});

test("uses nearest prior timestamp even when mutation timestamps are not monotonic", () => {
  const result = resolveActivitySnapshotSequence(
    activity({ startAt: "2026-04-26T12:00:10.000Z" }),
    [
      mutation(1, "2026-04-26T12:00:00.000Z"),
      mutation(2, "2026-04-26T12:00:15.000Z"),
      mutation(3, "2026-04-26T12:00:05.000Z"),
    ],
  );

  assert.equal(result, 3);
});

test("ignores invalid mutation timestamps while considering later valid candidates", () => {
  const result = resolveActivitySnapshotSequence(
    activity({ startAt: "2026-04-26T12:00:10.000Z" }),
    [
      mutation(1, "2026-04-26T12:00:00.000Z"),
      mutation(2, "2026-04-26T12:00:15.000Z"),
      mutation(3, "not-a-date"),
      mutation(4, "2026-04-26T12:00:05.000Z"),
    ],
  );

  assert.equal(result, 4);
});

test("returns null when no mutation can represent activity time", () => {
  const result = resolveActivitySnapshotSequence(
    activity({ startAt: "2026-04-26T12:00:10.000Z" }),
    [mutation(1, "2026-04-26T12:00:15.000Z")],
  );

  assert.equal(result, null);
});

test("ignores invalid mutation timestamps and returns null for invalid activity timestamps", () => {
  assert.equal(
    resolveActivitySnapshotSequence(
      activity({ startAt: "not-a-date" }),
      [mutation(1, "2026-04-26T12:00:00.000Z")],
    ),
    null,
  );

  assert.equal(
    resolveActivitySnapshotSequence(
      activity({ startAt: "2026-04-26T12:00:10.000Z" }),
      [
        mutation(1, "not-a-date"),
        mutation(2, "2026-04-26T12:00:05.000Z"),
      ],
    ),
    2,
  );
});
