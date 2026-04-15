import type { ContextEventPayload } from "@/lib/contracts/contextEvents";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "tool_call" }>;
  startedAt: string | null;
  completedAt: string | null;
}

export function ToolCallEvent({ payload, startedAt, completedAt }: Props) {
  return (
    <details className="rounded border border-amber-200 bg-amber-50 p-2 text-sm">
      <summary className="cursor-pointer font-medium text-amber-800">
        {payload.tool_name}
        {startedAt && completedAt && (
          <span className="ml-2 text-xs text-amber-500">
            {Math.round(
              (new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 100,
            ) / 10}
            s
          </span>
        )}
      </summary>
      <pre className="mt-1 text-xs">{JSON.stringify(payload.args, null, 2)}</pre>
    </details>
  );
}
