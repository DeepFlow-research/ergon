import assert from "node:assert/strict";
import test from "node:test";

import type { RunActivity } from "./types";
import { stackActivities } from "./stackLayout";

function activity(
  id: string,
  startAt: string,
  endAt: string | null,
  actor: string | null = null,
): RunActivity {
  return {
    id,
    kind: "execution",
    label: id,
    taskId: id,
    sequence: null,
    startAt,
    endAt,
    isInstant: endAt === null,
    actor,
    sourceKind: "execution.span",
    metadata: {},
  };
}

test("stackActivities allocates rows by time overlap and reuses rows", () => {
  const layout = stackActivities([
    activity("a", "2026-04-26T12:00:00.000Z", "2026-04-26T12:00:10.000Z", "agent-a"),
    activity("b", "2026-04-26T12:00:05.000Z", "2026-04-26T12:00:12.000Z", "agent-b"),
    activity("c", "2026-04-26T12:00:12.000Z", "2026-04-26T12:00:15.000Z", "agent-a"),
  ]);

  const rowById = new Map(layout.items.map((item) => [item.activity.id, item.row]));

  assert.equal(layout.rowCount, 2);
  assert.equal(layout.maxConcurrency, 2);
  assert.equal(rowById.get("a"), rowById.get("c"));
  assert.notEqual(rowById.get("a"), rowById.get("b"));
});

test("stackActivities reports three-way concurrency and does not group by actor", () => {
  const layout = stackActivities([
    activity("a", "2026-04-26T12:00:00.000Z", "2026-04-26T12:00:20.000Z", "agent-a"),
    activity("b", "2026-04-26T12:00:05.000Z", "2026-04-26T12:00:21.000Z", "agent-b"),
    activity("c", "2026-04-26T12:00:10.000Z", "2026-04-26T12:00:15.000Z", "agent-a"),
  ]);

  const rowsForAgentA = layout.items
    .filter((item) => item.activity.actor === "agent-a")
    .map((item) => item.row);

  assert.equal(layout.maxConcurrency, 3);
  assert.deepEqual(new Set(rowsForAgentA).size, 2);
});

test("stackActivities computes point-in-time concurrency instead of interval intersections", () => {
  const layout = stackActivities([
    activity("long", "2026-04-26T12:00:00.000Z", "2026-04-26T12:00:30.000Z"),
    activity("early", "2026-04-26T12:00:05.000Z", "2026-04-26T12:00:10.000Z"),
    activity("late", "2026-04-26T12:00:20.000Z", "2026-04-26T12:00:25.000Z"),
  ]);

  assert.equal(layout.maxConcurrency, 2);
});
