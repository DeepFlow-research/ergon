import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { TaskEvaluationState } from "@/lib/types";
import { EvaluationPanel } from "./EvaluationPanel";

function evaluation(): TaskEvaluationState {
  return {
    id: "evaluation-1",
    sampleId: "run-1",
    taskId: "task-1",
    evaluatorName: "rubric",
    aggregationRule: "weighted_sum",
    totalScore: 1,
    maxScore: 3,
    normalizedScore: 1 / 3,
    stagesEvaluated: 2,
    stagesPassed: 1,
    failedGate: "quality",
    createdAt: "2026-04-27T12:00:00.000Z",
    criterionResults: [
      {
        id: "pass",
        stageNum: 0,
        stageName: "quality",
        criterionNum: 0,
        criterionSlug: "pass",
        criterionType: "boolean",
        criterionDescription: "Good output",
        criterionName: "Good output",
        status: "passed",
        passed: true,
        weight: 1,
        contribution: 1,
        score: 1,
        maxScore: 1,
        feedback: "Solid.",
        modelReasoning: "The output meets the requirement.",
        skippedReason: null,
        evaluationInput: null,
        error: null,
        evaluatedActionIds: [],
        evaluatedResourceIds: [],
      },
      {
        id: "skip",
        stageNum: 1,
        stageName: "safety",
        criterionNum: 1,
        criterionSlug: "skip",
        criterionType: "boolean",
        criterionDescription: "Optional gate",
        criterionName: "Optional gate",
        status: "skipped",
        passed: false,
        weight: 1,
        contribution: 0,
        score: 0,
        maxScore: 1,
        feedback: null,
        modelReasoning: null,
        skippedReason: "No artifacts were produced.",
        evaluationInput: null,
        error: null,
        evaluatedActionIds: [],
        evaluatedResourceIds: [],
      },
      {
        id: "error",
        stageNum: 1,
        stageName: "safety",
        criterionNum: 2,
        criterionSlug: "error",
        criterionType: "boolean",
        criterionDescription: "Parser gate",
        criterionName: "Parser gate",
        status: "errored",
        passed: false,
        weight: 1,
        contribution: 0,
        score: 0,
        maxScore: 1,
        feedback: null,
        modelReasoning: null,
        skippedReason: null,
        evaluationInput: "payload",
        error: { message: "invalid json" },
        evaluatedActionIds: [],
        evaluatedResourceIds: [],
      },
    ],
  };
}

test("evaluation panel renders summary first and explicit skipped/error states", () => {
  const html = renderToStaticMarkup(React.createElement(EvaluationPanel, { evaluation: evaluation() }));

  assert.match(html, /Rubric summary/);
  assert.match(html, /33\.3%/);
  assert.match(html, /1 passed, 0 failed, 1 skipped, 1 errored/);
  assert.match(html, /Score composition/);
  assert.match(html, /Skipped/);
  assert.match(html, /No artifacts were produced/);
  assert.match(html, /Error/);
  assert.match(html, /invalid json/);
});
