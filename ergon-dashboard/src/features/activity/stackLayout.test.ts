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
    band: "work",
    label: id,
    taskId: id,
    sequence: null,
    startAt,
    endAt,
    isInstant: endAt === null,
    actor,
    sourceKind: "execution.span",
    metadata: {},
    lineage: { taskId: id, taskExecutionId: id },
    debug: { source: "execution.span", payload: { id } },
  };
}

function marker(id: string, startAt: string): RunActivity {
  return {
    id,
    kind: "graph",
    band: "graph",
    label: id,
    taskId: id,
    sequence: null,
    startAt,
    endAt: null,
    isInstant: true,
    actor: null,
    sourceKind: "graph.mutation",
    metadata: {},
    lineage: { taskId: id },
    debug: { source: "graph.mutation", payload: { id } },
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

test("stackActivities stacks instant markers when their visual footprints overlap", () => {
  const layout = stackActivities([
    activity("span", "2026-04-26T12:00:00.000Z", "2026-04-26T12:00:30.000Z"),
    marker("m1", "2026-04-26T12:00:05.000Z"),
    marker("m2", "2026-04-26T12:00:05.050Z"),
    marker("m3", "2026-04-26T12:00:10.000Z"),
  ]);
  const rowById = new Map(layout.items.map((item) => [item.activity.id, item.row]));

  assert.equal(layout.bands.find((band) => band.band === "work")?.rowCount, 1);
  assert.equal(layout.bands.find((band) => band.band === "graph")?.rowCount, 2);
  assert.equal(layout.rowCount, 3);
  assert.equal(layout.maxConcurrency, 1);
  assert.equal(rowById.get("m1"), 0);
  assert.equal(rowById.get("m2"), 1);
  assert.equal(rowById.get("m3"), 0);
});

test("stackActivities prevents marker and duration item covering inside non-work bands", () => {
  const layout = stackActivities([
    {
      ...activity("tool-span", "2026-04-26T12:00:05.000Z", "2026-04-26T12:00:10.000Z"),
      kind: "context",
      band: "tools",
    },
    {
      ...marker("tool-point", "2026-04-26T12:00:07.000Z"),
      kind: "context",
      band: "tools",
    },
    {
      ...marker("message-point", "2026-04-26T12:00:07.000Z"),
      kind: "message",
      band: "communication",
    },
    {
      ...marker("artifact-point", "2026-04-26T12:00:07.050Z"),
      kind: "artifact",
      band: "communication",
    },
  ]);
  const bandByName = new Map(layout.bands.map((band) => [band.band, band]));
  const rowById = new Map(layout.items.map((item) => [item.activity.id, item.row]));

  assert.equal(bandByName.get("tools")?.rowCount, 2);
  assert.equal(rowById.get("tool-span"), 0);
  assert.equal(rowById.get("tool-point"), 1);
  assert.equal(bandByName.get("communication")?.rowCount, 2);
  assert.notEqual(rowById.get("message-point"), rowById.get("artifact-point"));
});

test("stackActivities packs rows independently inside semantic bands", () => {
  const layout = stackActivities([
    { ...activity("work-a", "2026-04-26T12:00:00.000Z", "2026-04-26T12:00:20.000Z"), band: "work" },
    { ...activity("work-b", "2026-04-26T12:00:05.000Z", "2026-04-26T12:00:15.000Z"), band: "work" },
    { ...activity("tool-a", "2026-04-26T12:00:05.000Z", "2026-04-26T12:00:15.000Z"), kind: "context", band: "tools" },
  ]);

  const bandByName = new Map(layout.bands.map((band) => [band.band, band]));
  const rowById = new Map(layout.items.map((item) => [item.activity.id, item.row]));

  assert.equal(bandByName.get("work")?.rowCount, 2);
  assert.equal(bandByName.get("tools")?.rowCount, 1);
  assert.equal(rowById.get("work-a"), 0);
  assert.equal(rowById.get("work-b"), 1);
  assert.equal(rowById.get("tool-a"), 0);
});
