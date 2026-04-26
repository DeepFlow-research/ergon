import assert from "node:assert/strict";
import test from "node:test";

import type { RunActivity } from "./types";
import { resolveCurrentActivityId } from "./currentActivity";

function activity(id: string, startAt: string, sequence: number | null = null): RunActivity {
  return {
    id,
    kind: "graph",
    band: "graph",
    label: id,
    taskId: null,
    sequence,
    startAt,
    endAt: null,
    isInstant: true,
    actor: null,
    sourceKind: "graph.mutation",
    metadata: {},
    lineage: {},
    debug: { source: "graph.mutation", payload: { id } },
  };
}

test("resolveCurrentActivityId chooses latest activity at or before cursor time", () => {
  assert.equal(
    resolveCurrentActivityId(
      [
        activity("before", "2026-04-26T12:00:05.000Z"),
        activity("current", "2026-04-26T12:00:08.000Z"),
        activity("after", "2026-04-26T12:00:09.000Z"),
      ],
      "2026-04-26T12:00:08.500Z",
    ),
    "current",
  );
});

test("resolveCurrentActivityId breaks timestamp ties by highest graph sequence", () => {
  assert.equal(
    resolveCurrentActivityId(
      [
        activity("older-seq", "2026-04-26T12:00:08.000Z", 10),
        activity("newer-seq", "2026-04-26T12:00:08.000Z", 14),
      ],
      "2026-04-26T12:00:08.000Z",
    ),
    "newer-seq",
  );
});

test("resolveCurrentActivityId does not choose future graph sequence at same timestamp", () => {
  assert.equal(
    resolveCurrentActivityId(
      [
        activity("current-seq", "2026-04-26T12:00:08.000Z", 10),
        activity("future-seq", "2026-04-26T12:00:08.000Z", 14),
      ],
      "2026-04-26T12:00:08.000Z",
      10,
    ),
    "current-seq",
  );
});

test("resolveCurrentActivityId returns null before the first activity", () => {
  assert.equal(
    resolveCurrentActivityId(
      [activity("after", "2026-04-26T12:00:09.000Z")],
      "2026-04-26T12:00:08.000Z",
    ),
    null,
  );
});
