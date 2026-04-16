"use client";

import { useState } from "react";
import { GenerationTurnState } from "@/lib/types";

interface GenerationTracePanelProps {
  turns: GenerationTurnState[];
  runId?: string;
}

function formatArgs(args: unknown): string {
  if (args === null || args === undefined) return "";
  if (typeof args === "object") {
    return Object.entries(args as Record<string, unknown>)
      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
      .join(", ");
  }
  return String(args);
}

function ToolCallEntry({ tc }: { tc: { tool_call_id: string; tool_name: string; args: unknown } }) {
  const argsStr = formatArgs(tc.args);
  const isLong = argsStr.length > 120;

  return (
    <div className="rounded-lg border border-blue-100 bg-blue-50 px-2 py-2 font-mono text-xs dark:border-blue-900/40 dark:bg-blue-950/30">
      <div className="flex flex-wrap items-baseline gap-0.5">
        <span className="font-semibold text-blue-700 dark:text-blue-300">{tc.tool_name}</span>
        <span className="text-gray-500 dark:text-gray-400">(</span>
        {isLong ? (
          <details className="inline">
            <summary className="inline cursor-pointer list-none text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
              <span className="italic">args…</span>
            </summary>
            <span className="block whitespace-pre-wrap break-all pl-2 text-gray-600 dark:text-gray-400">
              {argsStr}
            </span>
          </details>
        ) : (
          <span className="text-gray-600 dark:text-gray-400">{argsStr}</span>
        )}
        <span className="text-gray-500 dark:text-gray-400">)</span>
      </div>
    </div>
  );
}

function formatTurnTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      fractionalSecondDigits: 3,
    });
  } catch {
    return null;
  }
}

function TurnCard({ turn }: { turn: GenerationTurnState }) {
  const [showRaw, setShowRaw] = useState(false);
  const hasToolCalls = turn.toolCalls && turn.toolCalls.length > 0;
  const turnTime = formatTurnTime(turn.at ?? null);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
          Turn {turn.turnIndex}
        </span>
        {turnTime && (
          <span
            className="font-mono text-[10px] tabular-nums text-gray-400 dark:text-gray-500"
            title={turn.at ?? undefined}
          >
            {turnTime}
          </span>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500">|</span>
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
          {turn.workerName || turn.workerBindingKey}
        </span>
        {turn.policyVersion !== null && turn.policyVersion !== undefined && (
          <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
            {turn.policyVersion}
          </span>
        )}
        <button
          type="button"
          onClick={() => setShowRaw(!showRaw)}
          className="ml-auto text-[10px] font-medium text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
        >
          {showRaw ? "Hide raw" : "Show raw"}
        </button>
      </div>

      <div className="space-y-2 p-3">
        {/* Tool calls are the primary content — rendered first and prominently */}
        {hasToolCalls && (
          <div>
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
              Tool Calls ({turn.toolCalls!.length})
            </div>
            <div className="space-y-1.5">
              {turn.toolCalls!.map((tc, i) => (
                <ToolCallEntry key={`${tc.tool_call_id}-${i}`} tc={tc} />
              ))}
            </div>
          </div>
        )}

        {/* Response text is secondary — muted and collapsed when there are tool calls */}
        {turn.responseText && (
          hasToolCalls ? (
            <details>
              <summary className="cursor-pointer text-[10px] font-medium text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                Model response text
              </summary>
              <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-gray-500 dark:text-gray-400">
                {turn.responseText}
              </p>
            </details>
          ) : (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                Response
              </div>
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-600 dark:text-gray-300">
                {turn.responseText}
              </p>
            </div>
          )
        )}

        {!turn.responseText && !hasToolCalls && (
          <p className="text-sm italic text-gray-400 dark:text-gray-500">
            No response text or tool calls recorded.
          </p>
        )}

        {showRaw && (
          <details className="mt-2" open>
            <summary className="cursor-pointer text-[10px] font-medium text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
              Raw turn data
            </summary>
            <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-gray-50 p-2 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-400">
              {JSON.stringify(turn, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

export function GenerationTracePanel({ turns }: GenerationTracePanelProps) {
  if (turns.length === 0) {
    return (
      <div className="text-center py-6 text-gray-500 dark:text-gray-400">
        <p className="text-sm">Activity will appear as the worker executes.</p>
      </div>
    );
  }

  const grouped = new Map<string, GenerationTurnState[]>();
  for (const turn of turns) {
    const key = turn.workerBindingKey;
    const existing = grouped.get(key) ?? [];
    existing.push(turn);
    grouped.set(key, existing);
  }

  const groups = Array.from(grouped.entries());
  const isSingleAgent = groups.length === 1;

  return (
    <div className="space-y-4">
      {isSingleAgent ? (
        <div className="space-y-3">
          {groups[0][1]
            .sort((a, b) => a.turnIndex - b.turnIndex)
            .map((turn) => (
              <TurnCard key={`${turn.taskExecutionId}-${turn.turnIndex}`} turn={turn} />
            ))}
        </div>
      ) : (
        groups.map(([agentKey, agentTurns]) => (
          <div key={agentKey}>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              {agentKey}
            </h4>
            <div className="space-y-3">
              {agentTurns
                .sort((a, b) => a.turnIndex - b.turnIndex)
                .map((turn) => (
                  <TurnCard key={`${turn.taskExecutionId}-${turn.turnIndex}`} turn={turn} />
                ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
