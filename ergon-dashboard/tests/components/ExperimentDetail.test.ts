import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ExperimentDetail } from "../../src/components/experiments/ExperimentDetail";
import { buildExperimentState } from "../../src/lib/sample-state/dashboard";
import { fixtureExperimentDetail } from "../contracts/experiment-rest-contract.test";

test("experiment detail renders sample rows and environment contributions", () => {
  const html = renderToStaticMarkup(
    createElement(ExperimentDetail, { state: buildExperimentState(fixtureExperimentDetail) }),
  );

  assert.match(html, /mini-validation/);
  assert.match(html, /href="\/samples\/sample-1"/);
  assert.doesNotMatch(html, />Runs</);
});
