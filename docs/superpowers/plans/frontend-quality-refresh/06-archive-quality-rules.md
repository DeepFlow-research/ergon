# PR 6 — Archive Cleanup And Quality Rules

## Purpose

Close the stack by preserving the useful lessons from the old design archive and
making future frontend work easier for humans and agents to verify.

## Scope

- Preserve `../ergon_fe_design_system` as a historical archive outside this PR
  stack.
- Move durable references into repo docs and RFC assets.
- Update dashboard architecture docs with frontend quality invariants.
- Add an LLM-facing note for running dashboard tests and screenshots.

## Likely Files

```text
docs/architecture/05_dashboard.md
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/README.md
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/*
docs/superpowers/plans/frontend-quality-refresh/*
CLAUDE.md
AGENTS.md
README.md
```

Only touch agent memory/instruction files that actually exist in the repo.

## Implementation Steps

1. Apply archive policy:
   - keep the old folder outside repo as a historical source;
   - keep selected screenshots in the RFC `assets/` folder as the canonical
     in-repo references;
   - do not delete or move the old archive in this stack unless a separate
     cleanup task explicitly asks for it;
   - mark cohort-era vocabulary as historical wherever it is referenced.
2. Update `docs/architecture/05_dashboard.md` with accepted quality invariants:
   - experiment language only;
   - tokenized surfaces;
   - evaluation state visible as structured UI;
   - screenshot review required for key dashboard surfaces.
3. Add LLM-facing test guidance if the repo has a suitable agent memory file:
   - `ergon start`;
   - `ergon test smoke`;
   - `pnpm -C ergon-dashboard run test:unit`;
   - Playwright screenshot commands.
4. Remove or clearly mark stale cohort-era design references that could mislead
   future implementation.

## UX Verification

Product tasks:

- Can a future agent find the frontend quality rules?
- Can a reviewer find the reference images?
- Is stale cohort vocabulary clearly historical and not product-current?

Screenshots:

- No new product screenshots required unless docs render images incorrectly.

## Tests

```sh
pnpm -C ergon-dashboard run test:unit
```

Run broader tests only if code changes land in this PR.

## Acceptance

- Architecture docs capture accepted frontend quality invariants.
- Future agents have an obvious test/screenshot workflow.
- The useful archive lessons live in repo docs or implemented product code.
- Stale cohort-era archive vocabulary is not treated as current UI language.
