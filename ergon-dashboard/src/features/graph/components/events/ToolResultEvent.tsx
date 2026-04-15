import type { ContextEventPayload } from "@/lib/contracts/contextEvents";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "tool_result" }>;
}

export function ToolResultEvent({ payload }: Props) {
  return (
    <details
      className={`rounded border p-2 text-sm ${
        payload.is_error ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50"
      }`}
    >
      <summary
        className={`cursor-pointer font-medium ${payload.is_error ? "text-red-700" : "text-green-700"}`}
      >
        {payload.tool_name} result
        {payload.is_error && (
          <span className="ml-2 text-xs text-red-500">error</span>
        )}
      </summary>
      <pre className="mt-1 text-xs">{JSON.stringify(payload.result, null, 2)}</pre>
    </details>
  );
}
