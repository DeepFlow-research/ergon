# PRD 00: CLI Hygiene Audit And Dead Code Cleanup

## Goal

Remove obvious dead code, stale command surface, and accidental drift from
`ergon_cli` before the larger domain refactor begins.

This PRD is intentionally a pre-refactor cleanup. Its purpose is to avoid
moving dead compatibility helpers, ignored flags, stale static catalogues, or
hardcoded local knowledge into the new domain structure.

## Problem

The CLI package is lint-clean, but several files contain code that is dead,
misleading, stale, or too weakly owned to preserve during refactor.

The highest-risk examples are:

- no-op bootstrap functions that are still wired into `main.py`
- parsed flags that are never used
- workflow actions exposed by argparse but not implemented for real execution
- static discovery rows that have drifted from builtins slugs
- benchmark sandbox template paths hardcoded directly in command code
- type-only wrappers that add ceremony without improving safety
- direct database/session imports inside command handlers

These issues make the CLI feel chaotic because the command surface promises
more than the implementation owns, and because operational details are mixed
with domain-facing command behavior.

## Non-Goals

This PRD does not perform the full CLI domain restructure.

It should not:

- move every command into the target `domains/` tree
- introduce the final shared rendering/error framework
- rewrite persistence-backed commands onto core views/runtime services
- redesign onboarding or benchmark metadata ownership in one pass

Those belong in later PRDs. This pass should make the current package cleaner
and prevent known-bad code from being carried forward.

## Proposed Cleanup Items

### 1. Delete no-op bootstrap compatibility code

Problem:

`ergon_cli.bootstrap.register_and_publish_builtins()` is a no-op retained after
object-bound builtins stopped needing explicit CLI publication. `main.py` also
defines `register_default_components()` as a second no-op.

Solution:

Delete both no-op functions and remove their conditional calls from `main.py`.
If a compatibility note is still useful, keep it in docs rather than executable
code.

Proposed code and location:

| Action | Current Location | Target |
| --- | --- | --- |
| Delete no-op builtin publication helper | `ergon_cli/bootstrap.py` | remove file if no imports remain |
| Delete no-op default component helper | `ergon_cli/main.py` | remove function |
| Remove conditional bootstrap calls | `ergon_cli/main.py` | direct dispatch only |

Acceptance:

- `rg "register_and_publish_builtins|register_default_components"` returns no
  production references.
- CLI startup behavior is unchanged.

### 2. Fix or remove unused command flags

Problem:

Several argparse flags are exposed but ignored. This creates false affordances
and makes tests less trustworthy.

Known cases:

| Flag | Current Location | Problem |
| --- | --- | --- |
| `doctor --verbose` | `ergon_cli/main.py`, `commands/doctor.py` | parsed but unused |
| `workflow resource-list --explain` | `ergon_cli/main.py`, `commands/workflow.py` | parsed but unused |
| `workflow task-tree --parent-task-id` | `commands/workflow.py` | PR #91 standardizes on task identity; add a regression test so parser/handler naming does not drift again |
| `workflow add-task --depends-on-task-slug` | older `commands/workflow.py` surfaces | removed by the PR #91 base; keep it out of the human CLI |

Solution:

For each flag, either implement the promised behavior or remove the flag. The
default choice should be removal unless the behavior is clearly part of the
near-term workflow UX.

Proposed code and location:

| Domain | Proposed Change |
| --- | --- |
| doctor | Remove `--verbose`, or thread it into a typed `DoctorCommand(verbose: bool)` and produce extra check details. |
| workflow | Keep `parent_task_id` argument handling covered if `task-tree` remains. |
| workflow | Remove `--explain`, or implement explanation output for resource listing. |
| workflow | Either pass dependency slugs into the workflow service or remove `--depends-on-task-slug` from non-dry-run command surface. |

Acceptance:

- No argparse flag is parsed without a production use or an explicit test that
  documents no-op compatibility behavior.
- Tests cover `workflow task-tree --parent-task-id`.
- Tests cover the chosen behavior for `--depends-on-task-slug`.

### 3. Align workflow parser actions with implementation

Problem:

`workflow` exposes actions including `add-edge`, `restart-task`, and
`abandon-task`, but non-dry-run execution only implements `add-task`.

Solution:

Do one of:

- remove unsupported actions from the live parser until implemented
- keep them only under `--dry-run`, with clear validation
- implement the corresponding service calls

Proposed code and location:

| Action | Current Location | Target |
| --- | --- | --- |
| Validate supported action set | `ergon_cli/commands/workflow.py` | short-term local guard |
| Later typed command models | `ergon_cli/domains/workflow/models.py` | one command model per action |
| Later executor split | `ergon_cli/domains/workflow/executor.py` | no parser-only actions |

Acceptance:

- A user cannot invoke a non-dry-run workflow action that silently does nothing
  or raises an implementation surprise.
- Tests cover each action exposed by argparse.

### 4. Replace stale static discovery rows

Problem:

`ergon_cli.discovery` hardcodes benchmark, worker, and evaluator rows. At least
the worker slugs appear stale relative to builtins naming.

Examples:

- CLI discovery lists `react-worker`
- builtins docs/code use `react-v1`
- CLI discovery lists `training-stub-worker`
- builtins docs/code use `training-stub`

Solution:

Short term, correct the rows and add tests that compare known builtins slugs.
Long term, replace static CLI discovery with metadata from `ergon_builtins`.

Proposed code and location:

| Phase | Proposed Location |
| --- | --- |
| Short-term corrected rows | `ergon_cli/discovery/__init__.py` |
| Long-term CLI catalogue service | `ergon_cli/domains/discovery/service.py` or domain-local list commands |
| Source of truth | `ergon_builtins` benchmark/worker/evaluator metadata |

Acceptance:

- `ergon worker list` and `ergon evaluator list` show slugs that are valid for
  the current builtins package.
- Tests fail if static rows drift from builtins metadata that is available in
  process.

### 5. Move benchmark sandbox template knowledge out of command code

Problem:

`commands/benchmark.py` embeds sandbox template paths using
`Path(__file__).parents[3]`. This is brittle and makes the CLI own knowledge
that belongs to benchmark definitions or a benchmark-specific adapter.

Solution:

Short term, move template lookup into a small benchmark-local helper so command
handlers do not contain path arithmetic. Long term, expose sandbox template
metadata from `ergon_builtins` and have the CLI consume that.

Proposed code and location:

| Phase | Proposed Location |
| --- | --- |
| Short-term helper | `ergon_cli/commands/benchmark_templates.py` or `ergon_cli/domains/benchmarks/templates.py` during refactor |
| Long-term source | `ergon_builtins` benchmark metadata |
| CLI command | `ergon_cli/domains/benchmarks/commands.py` |

Acceptance:

- No direct `Path(__file__).parents[...]` sandbox template lookup remains in a
  command handler.
- Adding a benchmark sandbox template does not require editing generic command
  dispatch code.

### 6. Remove type theater around build logs

Problem:

`BuildLog(Protocol)` in `commands/benchmark.py` only requires `__str__`. It
does not document meaningful behavior and gives a false sense of type safety.

Solution:

Replace with `object` and stringify at the boundary, or import/use the real E2B
log type if available without coupling the CLI too tightly.

Proposed code and location:

| Action | Current Location | Target |
| --- | --- | --- |
| Remove `BuildLog` protocol | `ergon_cli/commands/benchmark.py` | inline `object` callback |
| Later typed E2B adapter | `ergon_cli/domains/benchmarks/service.py` | hide SDK-specific callback detail |

Acceptance:

- No one-off protocol exists solely to model `str(x)`.
- Build log printing behavior remains unchanged.

### 7. Decide ownership for CLI-local environment keys

Problem:

`onboarding/env_writer.py` includes operational keys such as Tailscale settings.
They may be valid, but they currently appear as unowned static `.env` sections.

Solution:

Classify each env key as one of:

- core runtime
- model/provider runtime
- benchmark/evaluation runtime
- infra/training runtime
- local networking/dev convenience

Keep the keys that are still valid, but move the ownership explanation into a
typed profile or onboarding metadata layer.

Proposed code and location:

| Phase | Proposed Location |
| --- | --- |
| Short-term comments/section cleanup | `ergon_cli/onboarding/env_writer.py` |
| Later typed env key catalogue | `ergon_cli/domains/onboarding/profile.py` |
| Later writer | `ergon_cli/domains/onboarding/env_writer.py` |

Acceptance:

- Every env key written by onboarding has a named owner category.
- Local-only convenience keys are either documented as such or removed.

### 8. Reconcile onboarding dependency drift

Problem:

`onboarding/profile.py` duplicates benchmark dependency requirements and refers
to infra extras that may no longer match package metadata.

Solution:

Short term, verify the extras against package metadata and correct stale values.
Long term, source benchmark and infrastructure dependency recommendations from
the package/domain that owns them.

Proposed code and location:

| Dependency Knowledge | Current Location | Long-Term Owner |
| --- | --- | --- |
| benchmark Python packages | `ergon_cli/onboarding/profile.py` | `ergon_builtins` benchmark metadata |
| infra/training extras | `ergon_cli/onboarding/profile.py` | package metadata or infra domain metadata |

Acceptance:

- Recommended extras install successfully from the repo.
- Onboarding tests cover at least one profile that selects infra/training
  dependencies.

### 9. Mark persistence-backed command handlers for later service extraction

Problem:

`commands/run.py` and `commands/experiment.py` directly import database/session
internals. This is larger than a hygiene patch, but it should be explicitly
marked so the refactor does not preserve the current boundary.

Solution:

Do not rewrite these in the hygiene PR unless tiny. Add the service extraction
to the later CLI domain PRDs and avoid worsening the direct DB coupling.

Proposed code and location:

| Command Area | Current Location | Later Target |
| --- | --- | --- |
| runs | `ergon_cli/commands/run.py` | `ergon_cli/domains/runs/service.py` delegating to core views/runtime services |
| experiments | `ergon_cli/commands/experiment.py` | `ergon_cli/domains/experiments/service.py` delegating to core views services |

Acceptance:

- Hygiene PR does not add new direct DB/session imports.
- Later refactor PR has a specific task to replace direct persistence reads.

## Test Plan

Add or update focused CLI unit tests for:

- no bootstrap compatibility calls during startup
- `doctor` parser behavior after `--verbose` decision
- `workflow task-tree --parent-task-id`
- workflow unsupported action behavior
- workflow dependency slug behavior
- worker/evaluator list slugs
- benchmark setup template lookup helper

Run:

```bash
uv run ruff check ergon_cli/ergon_cli
uv run pytest ergon_cli/tests/unit/cli
```

## Proposed PR Shape

This should be one small PR before the larger CLI domain migration:

1. Delete no-op bootstrap/default component code.
2. Fix or remove ignored flags.
3. Align workflow parser actions with implementation.
4. Correct stale discovery slugs.
5. Extract benchmark template lookup out of command code.
6. Remove `BuildLog(Protocol)`.
7. Add focused tests for the above.

## Open Questions

- Should `workflow add-edge`, `restart-task`, and `abandon-task` be implemented
  now, or removed until the workflow domain refactor?
- Should `doctor --verbose` be kept as a real detail mode, or deleted for now?
- Should static discovery survive as a compatibility shim, or should this PR
  immediately read from builtins metadata?
- Are Tailscale env keys still part of supported local development, or are they
  local operational residue?

## Acceptance Criteria

- Obvious no-op compatibility code is deleted.
- No CLI flag in the audited set is silently ignored.
- Workflow parser actions match executable behavior.
- Discovery rows no longer advertise stale builtins slugs.
- Benchmark sandbox template lookup no longer lives inline in the command
  handler.
- The cleanup is covered by focused unit tests and does not change unrelated CLI
  behavior.
