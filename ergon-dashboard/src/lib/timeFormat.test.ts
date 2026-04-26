import assert from "node:assert/strict";
import test from "node:test";

import { formatClockTime, formatClockTimeMs, formatClockTimeSeconds } from "./timeFormat";

test("formatClockTime is stable for UTC timestamps regardless of runtime local timezone", () => {
  assert.equal(formatClockTime("2026-04-26T10:24:15.000Z"), "10:24");
});

test("formatClockTime returns dash for invalid timestamps", () => {
  assert.equal(formatClockTime("not-a-date"), "—");
  assert.equal(formatClockTime(Number.NaN), "—");
});

test("formatClockTimeMs includes seconds and milliseconds with stable timezone", () => {
  assert.equal(formatClockTimeMs("2026-04-26T10:24:15.123Z"), "10:24:15.123");
});

test("formatClockTimeSeconds includes seconds with stable timezone", () => {
  assert.equal(formatClockTimeSeconds("2026-04-26T10:24:15.123Z"), "10:24:15");
});
