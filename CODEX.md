# Ergon Codex Instructions

Follow `CLAUDE.md`; it is the canonical instruction file for this repository.
The May 2026 authoring API redesign failures are captured there under
**Agent regression guardrails**.

Before claiming a runtime, persistence, CLI, workflow, or dashboard harness
change is complete, verify the relevant end-to-end path and update
`docs/architecture/` when behavior or invariants change.

For dashboard frontend work, use the frontend quality invariants in
`docs/architecture/05_dashboard.md` and the screenshot-backed RFC under
`docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/`.
Prefer `ergon start`, `ergon test smoke`,
`pnpm -C ergon-dashboard run test:unit`, and Playwright fixed-viewport
screenshots for changed dashboard surfaces. Keep cohort-era language
historical; current product copy should use experiments, runs, tasks,
evaluations, and rubrics.
