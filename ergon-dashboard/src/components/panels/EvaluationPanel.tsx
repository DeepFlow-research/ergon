"use client";

import { TaskEvaluationState } from "@/lib/types";

function formatPercent(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case "passed":
      return "bg-emerald-50 text-emerald-700 ring-emerald-200";
    case "failed":
      return "bg-rose-50 text-rose-700 ring-rose-200";
    case "errored":
      return "bg-amber-50 text-amber-700 ring-amber-200";
    case "skipped":
      return "bg-slate-100 text-slate-600 ring-slate-200";
    default:
      return "bg-gray-100 text-gray-700 ring-gray-200";
  }
}

function EvaluationCriteriaEmpty({ detail }: { detail: string }) {
  return (
    <div
      className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-400"
      data-testid="evaluation-criteria-empty"
    >
      <p className="font-medium text-gray-700 dark:text-gray-200">
        No evaluation criteria recorded yet
      </p>
      <p className="mt-1 text-sm">{detail}</p>
    </div>
  );
}

export function EvaluationPanel({
  evaluation,
}: {
  evaluation: TaskEvaluationState | null;
}) {
  if (!evaluation) {
    return (
      <EvaluationCriteriaEmpty detail="Evaluation details will appear when a persisted evaluation payload is available." />
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Evaluator</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.evaluatorName}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Aggregation</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.aggregationRule}
          </div>
        </div>
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

      {evaluation.criterionResults.length === 0 ? (
        <EvaluationCriteriaEmpty detail="This task has no criterionResults in the persisted evaluation payload." />
      ) : (
        <div className="space-y-3">
          {evaluation.criterionResults.map((criterion) => (
            <div
              key={criterion.id}
              className="rounded-xl border border-gray-200 bg-white px-3 py-3 dark:border-gray-700 dark:bg-gray-900/40"
              data-testid={`evaluation-criterion-${criterion.id}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ring-1 ${statusBadgeClass(criterion.status)}`}
                      data-testid={`evaluation-criterion-status-${criterion.id}`}
                    >
                      {criterion.status}
                    </span>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {criterion.stageName}: {criterion.criterionDescription}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {criterion.criterionName} · {criterion.criterionType} · weight {criterion.weight}
                  </div>
                </div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">
                  {criterion.score} / {criterion.maxScore}
                  <div className="text-right text-[11px] font-normal text-gray-500 dark:text-gray-400">
                    contribution {criterion.contribution}
                  </div>
                </div>
              </div>
              {criterion.modelReasoning ? (
                <div className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:bg-gray-800/50 dark:text-gray-200">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Reasoning
                  </div>
                  <p className="whitespace-pre-wrap">{criterion.modelReasoning}</p>
                </div>
              ) : null}
              {criterion.skippedReason ? (
                <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                  Skipped: {criterion.skippedReason}
                </div>
              ) : null}
              {criterion.error ? (
                <pre
                  className="mt-2 max-h-32 overflow-auto rounded-lg bg-amber-50 p-2 text-xs text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-100"
                  data-testid={`evaluation-criterion-error-${criterion.id}`}
                >
                  {JSON.stringify(criterion.error, null, 2)}
                </pre>
              ) : null}
              {criterion.feedback ? (
                <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200">
                  {criterion.feedback}
                </p>
              ) : null}
              {criterion.evaluationInput ? (
                <details className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-800/50">
                  <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Evaluation input
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs text-gray-700 dark:text-gray-200">
                    {criterion.evaluationInput}
                  </pre>
                </details>
              ) : null}
              {(criterion.evaluatedActionIds.length > 0 || criterion.evaluatedResourceIds.length > 0) && (
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                  {criterion.evaluatedActionIds.map((id) => (
                    <span key={`action-${id}`} className="rounded-full bg-gray-100 px-2 py-0.5 dark:bg-gray-800">
                      action {id}
                    </span>
                  ))}
                  {criterion.evaluatedResourceIds.map((id) => (
                    <span key={`resource-${id}`} className="rounded-full bg-gray-100 px-2 py-0.5 dark:bg-gray-800">
                      resource {id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
