import type { ContextEventPayload } from "@/lib/contracts/contextEvents";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "system_prompt" }>;
}

export function SystemPromptEvent({ payload }: Props) {
  return (
    <details className="rounded border border-gray-200 bg-gray-50 p-2 text-xs text-gray-500">
      <summary className="cursor-pointer font-medium">System Prompt</summary>
      <pre className="mt-1 whitespace-pre-wrap">{payload.text}</pre>
    </details>
  );
}
