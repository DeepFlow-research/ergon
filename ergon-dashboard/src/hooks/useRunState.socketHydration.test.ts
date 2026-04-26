import assert from "node:assert/strict";
import test from "node:test";

import { shouldRequestSocketSnapshot } from "./useRunState";

test("does not request socket full-state snapshot when REST or SSR state is already hydrated", () => {
  assert.equal(shouldRequestSocketSnapshot(true), false);
});

test("requests socket full-state snapshot when no REST or SSR state is available yet", () => {
  assert.equal(shouldRequestSocketSnapshot(false), true);
});
