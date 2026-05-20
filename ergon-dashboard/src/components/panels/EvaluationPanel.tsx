"use client";

import React from "react";

import { evaluationToViewModel } from "@/features/evaluation/selectors";
import type { TaskEvaluationState } from "@/lib/types";

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
  const view = evaluationToViewModel(evaluation);

  if (!view) {
    return (
      <EvaluationCriteriaEmpty detail="Evaluation details will appear when a persisted evaluation payload is available." />
    );
  }

  return (
    <div className="space-y-3">
      <section
        className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] p-3"
        data-testid="evaluation-summary"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
              Rubric summary
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${statusBadgeClass(
                  view.summary.status === "passing"
                    ? "passed"
                    : view.summary.status === "failing"
                      ? "failed"
                      : view.summary.status,
                )}`}
                data-testid="evaluation-summary-status"
              >
                {view.summary.status}
              </span>
              <span className="text-sm font-semibold text-[var(--ink)]">
                {view.summary.criteriaLabel}
              </span>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono text-2xl font-semibold tabular-nums text-[var(--ink)]">
              {view.summary.scoreLabel}
            </div>
            <div className="text-[10px] text-[var(--muted)]">normalized score</div>
          </div>
        </div>
      </section>

      <section
        className="grid gap-2 sm:grid-cols-3"
        aria-label="Score composition"
        data-testid="evaluation-composition"
      >
        <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            Score composition
          </div>
          <div className="mt-1 font-mono text-sm font-semibold text-[var(--ink)]">
            {view.composition.totalScoreLabel}
          </div>
        </div>
        <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            Aggregation
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-[var(--ink)]">
            {view.composition.aggregationRule}
          </div>
        </div>
        <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            Stages / gate
          </div>
          <div className="mt-1 text-sm font-semibold text-[var(--ink)]">
            {view.composition.stagesLabel} · {view.summary.failedGateLabel}
          </div>
        </div>
      </section>

      {view.criteria.length === 0 ? (
        <EvaluationCriteriaEmpty detail="This task has no criterionResults in the persisted evaluation payload." />
      ) : (
        <div className="space-y-2" data-testid="evaluation-criteria">
          {view.criteria.map((criterion) => (
            <div
              key={criterion.id}
              className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-3 py-2"
              data-testid={`evaluation-criterion-${criterion.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${statusBadgeClass(criterion.status)}`}
                      data-testid={`evaluation-criterion-status-${criterion.id}`}
                    >
                      {criterion.stateLabel}
                    </span>
                    <div className="truncate font-medium text-[var(--ink)]">
                      {criterion.title}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-[var(--muted)]">
                    {criterion.stageLabel} · {criterion.typeLabel} · weight {criterion.weightLabel}
                  </div>
                </div>
                <div className="shrink-0 text-right text-sm font-semibold text-[var(--ink)]">
                  {criterion.scoreLabel}
                  <div className="text-right text-[11px] font-normal text-gray-500 dark:text-gray-400">
                    contribution {criterion.contributionLabel}
                  </div>
                </div>
              </div>
              {criterion.modelReasoning ? (
                <div className="mt-2 rounded-[var(--radius-sm)] bg-[var(--paper)] px-3 py-2 text-sm text-[var(--ink)]">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Reasoning
                  </div>
                  <p className="whitespace-pre-wrap">{criterion.modelReasoning}</p>
                </div>
              ) : null}
              {criterion.skippedReason ? (
                <div className="mt-2 rounded-[var(--radius-sm)] border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
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
                <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--ink)]">
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
