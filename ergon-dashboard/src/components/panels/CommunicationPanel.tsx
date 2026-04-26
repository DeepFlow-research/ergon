"use client";

import { useEffect, useMemo, useState } from "react";

import { CommunicationThreadState } from "@/lib/types";
import { formatClockTimeSeconds } from "@/lib/timeFormat";

function formatTime(timestamp: string): string {
  return formatClockTimeSeconds(timestamp);
}

function speakerLabel(agentId: string): string {
  const suffix = agentId.split(":").pop() ?? agentId;
  return suffix.replaceAll("_", " ").replaceAll("-", " ");
}

function threadSummary(thread: CommunicationThreadState): string {
  if (thread.summary) return thread.summary;
  const participants = participantLabels(thread);
  if (thread.messages.length === 0) {
    return participants.length > 0
      ? `Thread between ${participants.join(", ")}.`
      : "No messages are visible at this point in the run.";
  }
  const first = thread.messages[0];
  const preview = first.content.length > 96 ? `${first.content.slice(0, 96)}...` : first.content;
  return `${thread.messages.length} message${thread.messages.length === 1 ? "" : "s"} · ${preview}`;
}

function participantLabels(thread: CommunicationThreadState): string[] {
  const ids = new Set<string>([thread.agentAId, thread.agentBId]);
  for (const message of thread.messages) {
    ids.add(message.fromAgentId);
    ids.add(message.toAgentId);
  }
  return [...ids].filter(Boolean).map(speakerLabel);
}

function messageAlignment(message: CommunicationThreadState["messages"][number], index: number) {
  return index % 2 === 0 || message.fromAgentId === "parent" ? "justify-start" : "justify-end";
}

export function CommunicationPanel({
  threads,
}: {
  threads: CommunicationThreadState[];
}) {
  const sortedThreads = useMemo(
    () =>
      [...threads].sort(
        (a, b) =>
          Date.parse(a.createdAt) - Date.parse(b.createdAt) ||
          a.topic.localeCompare(b.topic),
      ),
    [threads],
  );
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(
    sortedThreads[0]?.id ?? null,
  );

  useEffect(() => {
    if (sortedThreads.length === 0) {
      setSelectedThreadId(null);
      return;
    }
    if (!selectedThreadId || !sortedThreads.some((thread) => thread.id === selectedThreadId)) {
      setSelectedThreadId(sortedThreads[0].id);
    }
  }, [selectedThreadId, sortedThreads]);

  if (threads.length === 0) {
    return (
      <div className="py-6 text-center text-[var(--muted)]">
        <p className="font-medium text-[var(--ink)]">No communication threads yet</p>
        <p className="text-sm">Messages will appear here as threads evolve.</p>
      </div>
    );
  }

  const selectedThread =
    sortedThreads.find((thread) => thread.id === selectedThreadId) ?? sortedThreads[0] ?? null;
  const selectedMessages = selectedThread
    ? [...selectedThread.messages].sort((a, b) => a.sequenceNum - b.sequenceNum)
    : [];

  return (
    <div className="min-w-0 space-y-3">
      <div
        className="max-h-72 min-w-0 space-y-2 overflow-y-auto pr-1"
        aria-label="Communication thread list"
        data-testid="communication-thread-list"
      >
        {sortedThreads.map((thread) => {
          const selected = thread.id === selectedThread?.id;
          const participants = participantLabels(thread);
          return (
            <button
              key={thread.id}
              type="button"
              onClick={() => setSelectedThreadId(thread.id)}
              className={`w-full rounded-[var(--radius-sm)] border p-3 text-left transition ${
                selected
                  ? "border-[var(--accent)] bg-[var(--accent-soft)]/50 shadow-sm"
                  : "border-[var(--line)] bg-[var(--card)] hover:border-[var(--accent-soft)] hover:bg-[var(--paper)]"
              }`}
              data-testid="communication-thread-card"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-[var(--ink)]">
                    {thread.topic}
                  </div>
                  <div className="mt-1 line-clamp-2 break-words text-xs leading-4 text-[var(--muted)]">
                    {threadSummary(thread)}
                  </div>
                </div>
                <span className="shrink-0 rounded-full bg-[var(--paper)] px-2 py-0.5 font-mono text-[10px] text-[var(--muted)] ring-1 ring-[var(--line)]">
                  {thread.messages.length}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {participants.slice(0, 4).map((participant) => (
                  <span
                    key={participant}
                    className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-[var(--muted)] ring-1 ring-[var(--line)]"
                  >
                    {participant}
                  </span>
                ))}
              </div>
              <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-[var(--faint)]">
                <span>{formatTime(thread.createdAt)}</span>
                <span>{formatTime(thread.updatedAt)}</span>
              </div>
            </button>
          );
        })}
      </div>

      <div
        className="min-h-[240px] min-w-0 overflow-hidden rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)]"
        data-testid="communication-chat-trace"
      >
        {selectedThread && (
          <>
            <div className="border-b border-[var(--line)] bg-[var(--paper)] px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-[var(--ink)]">
                    {selectedThread.topic}
                  </div>
                  <div className="mt-1 break-words text-xs text-[var(--muted)]">
                    Started {formatTime(selectedThread.createdAt)}
                    {selectedThread.taskId ? ` · linked task ${selectedThread.taskId}` : ""}
                  </div>
                </div>
                <span className="shrink-0 rounded-full bg-[var(--card)] px-2 py-0.5 text-[10px] font-medium text-[var(--muted)] ring-1 ring-[var(--line)]">
                  {selectedMessages.length} message{selectedMessages.length === 1 ? "" : "s"}
                </span>
              </div>
              <p className="mt-2 break-words text-xs leading-4 text-[var(--muted)]">
                {threadSummary(selectedThread)}
              </p>
            </div>

            <div className="max-h-96 space-y-3 overflow-y-auto overflow-x-hidden bg-[var(--paper-2)] p-3">
              {selectedMessages.length === 0 && (
                <div className="py-8 text-center text-sm text-[var(--muted)]">
                  No messages are visible at this point in the run.
                </div>
              )}
              {selectedMessages.map((message, index) => (
                <div
                  key={message.id}
                  className={`flex ${messageAlignment(message, index)}`}
                  data-testid="communication-chat-message"
                >
                  <div
                    className={`max-w-[92%] min-w-0 overflow-hidden rounded-2xl px-3 py-2 shadow-sm ring-1 ${
                      index % 2 === 0
                        ? "rounded-tl-sm bg-white text-[var(--ink)] ring-[var(--line)]"
                        : "rounded-tr-sm bg-emerald-50 text-emerald-950 ring-emerald-100"
                    }`}
                    data-testid={`communication-message-${message.id}`}
                  >
                    <div className="flex items-center justify-between gap-3 text-[11px]">
                      <span className="font-semibold text-[var(--ink)]">
                        {speakerLabel(message.fromAgentId)}
                      </span>
                      <span className="font-mono text-[var(--faint)]">
                        {formatTime(message.createdAt)}
                      </span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-5">
                      {message.content}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-2 break-all font-mono text-[10px] text-[var(--faint)]">
                      <span>#{message.sequenceNum}</span>
                      {message.taskId && <span className="break-all">task {message.taskId}</span>}
                      {message.taskExecutionId && (
                        <span className="break-all">exec {message.taskExecutionId}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
