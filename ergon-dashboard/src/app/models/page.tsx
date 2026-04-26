export default function ModelsPage() {
  return (
    <div className="min-h-[60vh] bg-[var(--paper)]">
      <header className="border-b border-[var(--line)] bg-[var(--card)]">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            Workspace <span aria-hidden>◆</span>
          </span>
          <h1 className="mt-1 text-[26px] font-semibold leading-tight text-[var(--ink)]">
            Models
          </h1>
          <p className="mt-1.5 text-[13px] text-[var(--muted)]">
            View trained model checkpoints, evaluation scores, and deployment status.
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-12">
        <div className="rounded-[var(--radius)] border border-dashed border-[var(--line-strong)] bg-[var(--paper)] p-12 text-center">
          <div className="mx-auto mb-3 text-3xl text-[var(--faint)]">⊘</div>
          <h2 className="text-lg font-medium text-[var(--ink)]">Coming soon</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            The model registry is under development. Use the training page to track active sessions.
          </p>
        </div>
      </main>
    </div>
  );
}
