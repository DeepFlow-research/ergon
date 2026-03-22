"use client";

import { TaskEvaluationState } from "@/lib/types";

function formatPercent(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

export function EvaluationPanel({
  evaluation,
}: {
  evaluation: TaskEvaluationState | null;
}) {
  if (!evaluation) {
    return (
      <div className="text-center py-6 text-gray-500 dark:text-gray-400">
        <p>No evaluation yet</p>
        <p className="text-sm">Judgment surfaces will update when evaluation arrives.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Normalized</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatPercent(evaluation.normalizedScore)}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Total score</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.totalScore} / {evaluation.maxScore}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Stages passed</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.stagesPassed} / {evaluation.stagesEvaluated}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Failed gate</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.failedGate ?? "none"}
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {evaluation.criterionResults.map((criterion) => (
          <div
            key={criterion.id}
            className="rounded-xl border border-gray-200 bg-white px-3 py-3 dark:border-gray-700 dark:bg-gray-900/40"
            data-testid={`evaluation-criterion-${criterion.id}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="font-medium text-gray-900 dark:text-white">
                  {criterion.stageName}: {criterion.criterionDescription}
                </div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {criterion.criterionType}
                </div>
              </div>
              <div className="text-sm font-semibold text-gray-900 dark:text-white">
                {criterion.score} / {criterion.maxScore}
              </div>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200">
              {criterion.feedback}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
