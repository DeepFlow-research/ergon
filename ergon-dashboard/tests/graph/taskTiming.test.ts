import assert from "node:assert/strict";
import test from "node:test";

import {
  formatTaskWallTimestamp,
  getTaskTimingPrimaryLine,
} from "../../src/features/graph/utils/taskTiming";

test("getTaskTimingPrimaryLine returns wall duration when started and completed are set", () => {
  const line = getTaskTimingPrimaryLine({
    startedAt: "2026-03-18T12:00:00.000Z",
    completedAt: "2026-03-18T12:00:12.000Z",
  });
  assert.equal(line, "12.0s");
});

test("getTaskTimingPrimaryLine returns Started … when only started is set", () => {
  const line = getTaskTimingPrimaryLine({
    startedAt: "2026-03-18T12:00:00.000Z",
    completedAt: null,
  });
  assert.ok(line);
  assert.match(line, /^Started /);
});

test("getTaskTimingPrimaryLine returns null when task has not started", () => {
  assert.equal(
    getTaskTimingPrimaryLine({ startedAt: null, completedAt: null }),
    null,
  );
});

test("formatTaskWallTimestamp returns dateTime for valid ISO", () => {
  const out = formatTaskWallTimestamp("2026-03-18T12:00:00.000Z");
  assert.equal(out.dateTime, "2026-03-18T12:00:00.000Z");
  assert.ok(out.text.length > 0);
});

test("formatTaskWallTimestamp returns em dash for null", () => {
  assert.deepEqual(formatTaskWallTimestamp(null), { text: "—", dateTime: null });
});
