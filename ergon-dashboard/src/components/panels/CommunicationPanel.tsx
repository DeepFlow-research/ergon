"use client";

import { CommunicationThreadState } from "@/lib/types";

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function speakerLabel(agentId: string): string {
  const suffix = agentId.split(":").pop() ?? agentId;
  return suffix.replaceAll("_", " ");
}

export function CommunicationPanel({
  threads,
}: {
  threads: CommunicationThreadState[];
}) {
  if (threads.length === 0) {
    return (
      <div className="text-center py-6 text-gray-500 dark:text-gray-400">
        <p>No communication yet</p>
        <p className="text-sm">Messages will appear here as threads evolve.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {threads.map((thread) => (
        <div
          key={thread.id}
          className="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
        >
          <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium text-gray-900 dark:text-white">{thread.topic}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {speakerLabel(thread.agentAId)} ↔ {speakerLabel(thread.agentBId)}
                </div>
              </div>
              <div className="text-xs text-gray-400 dark:text-gray-500">
                {thread.messages.length} message{thread.messages.length === 1 ? "" : "s"}
              </div>
            </div>
          </div>
          <div className="max-h-80 space-y-3 overflow-y-auto bg-white p-3 dark:bg-gray-900">
            {thread.messages.map((message) => (
              <div
                key={message.id}
                className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/60"
                data-testid={`communication-message-${message.id}`}
              >
                <div className="flex items-center justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
                  <span className="font-medium">{speakerLabel(message.fromAgentId)}</span>
                  <span>{formatTime(message.createdAt)}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200">
                  {message.content}
                </p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
