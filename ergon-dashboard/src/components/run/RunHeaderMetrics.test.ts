import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RunHeaderMetrics } from "./RunHeaderMetrics";

test("run header metrics render strong values and unavailable states", () => {
  const html = renderToStaticMarkup(
    React.createElement(RunHeaderMetrics, {
      metrics: {
        tasks: { completed: 3, running: 1, failed: 1, total: 6 },
        tokens: null,
        costUsd: null,
        costObserved: false,
        score: null,
      },
    }),
  );

  assert.match(html, /3 \/ 6/);
  assert.match(html, /1 running/);
  assert.match(html, /1 failed/);
  assert.match(html, /Unavailable/);
  assert.match(html, /tokens not reported/);
  assert.match(html, /cost not observed/);
  assert.match(html, /score not reported/);
});

test("run header metrics render observed token cost and score values", () => {
  const html = renderToStaticMarkup(
    React.createElement(RunHeaderMetrics, {
      metrics: {
        tasks: { completed: 8, running: 0, failed: 0, total: 8 },
        tokens: 9820,
        costUsd: 0.0284,
        costObserved: true,
        score: 0.75,
      },
    }),
  );

  assert.match(html, /9\.8K/);
  assert.match(html, /\$0\.0284/);
  assert.match(html, /75\.0%/);
  assert.doesNotMatch(html, /Unavailable/);
});
