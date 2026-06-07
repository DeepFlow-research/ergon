import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { SampleDetail } from "../../src/components/samples/SampleDetail";
import { buildSampleState } from "../../src/lib/sample-state/dashboard";
import { fixtureSampleDetail, fixtureSampleEvents, fixtureSampleGraph } from "../contracts/sample-rest-contract.test";

test("sample detail renders breadcrumb and typed events", () => {
  const html = renderToStaticMarkup(
    createElement(SampleDetail, {
      state: buildSampleState({
        detail: fixtureSampleDetail,
        events: fixtureSampleEvents.items,
        graph: fixtureSampleGraph,
      }),
    }),
  );

  assert.match(html, new RegExp(`href="/experiments/${fixtureSampleDetail.experimentId}"`));
  assert.match(html, /task.added/);
  assert.doesNotMatch(html, /mutation/i);
});
