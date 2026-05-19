# PR 8 — Lifecycle CLI Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Round out the lifecycle / observation commands the CLI keeps after PR 6.5 killed the authoring route.  No new abstractions.  No factory dispatch.  No per-benchmark CLI registration burden.

**Context:** PR 6.5 made the call (and recorded the rationale in `docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md`) that the CLI has **exactly one role**: lifecycle and observation of persisted state.  Authoring is Python-only.  PR 6.5 deleted the `ergon experiment define` / `ergon experiment run` *authoring* commands — but kept the *observation* commands (`experiment show <UUID>`, `experiment list`, `run list`, `run cancel`) that operate on persisted state.  PR 8 fills in the remaining gaps: a single-run status command, an experiment-tag-based filter on `run list`, and tag-grouping commands that surface `BenchmarkDefinitionRecord.experiment` (which is otherwise unobservable from the CLI today).

**Scope (much smaller than the original plan):** three new commands and one new flag.  Each is a thin wrapper around an existing repository read.  No DTOs, no factory registries, no new abstractions.

**Tech Stack:** argparse CLI handlers, existing repositories (`DefinitionRepository`, direct `RunRecord` reads, `ExperimentReadService`), pytest CLI tests.

---

## Files

**Create:**

```text
ergon_cli/tests/unit/cli/test_run_cli.py        # tests for the new commands
```

**Modify:**

```text
ergon_cli/ergon_cli/commands/run.py             # add `status`, --experiment filter
ergon_cli/ergon_cli/commands/experiment.py      # add `tags`, `by-tag`
ergon_cli/ergon_cli/main.py                     # register new subparsers
ergon_cli/tests/unit/cli/test_experiment_cli.py # tests for new commands
ergon_core/ergon_core/core/application/experiments/repository.py  # add tag helpers
ergon_core/ergon_core/core/application/workflows/runs.py          # add list helpers if missing
```

## Current State (after PR 6.5 + PR 7)

After PR 7 lands (one layer up from this PR):

- The public `Experiment` wrapper class is gone (PR 6.5).
- `persist_benchmark(benchmark) -> DefinitionHandle` is the authoring API
  (module-level function in `ergon_core.api`). Identity fields (``name``,
  ``description``, ``metadata``, ``created_by``) are read off the
  ``Benchmark`` instance directly — no kwargs to `persist_benchmark`.
- `BenchmarkDefinitionRecord` is the persisted legacy row (table
  ``experiments``), with an `experiment: str | None` column. Multiple
  records sharing the same `experiment` tag belong to the same logical
  experiment.  No `Benchmark(experiment=...)` constructor kwarg exists
  today; tagging is currently a write-side-only column populated by the
  cohort / test harness.
- `ExperimentDefinition` is the canonical v2 row (table
  ``experiment_definitions``) with `name`/`description`/`created_by`
  columns added in PR 7.
- The CLI **already has** these observation commands (kept by PR 6.5):
  - `ergon experiment show <UUID>` — full detail via `ExperimentReadService.get_experiment`
  - `ergon experiment list --limit N` — list summaries via `ExperimentReadService.list_experiments`
  - `ergon run list --limit N --status S` — direct `RunRecord` query
  - `ergon run cancel <UUID>` — wraps `workflows.runs.cancel_run` (sync)
- The CLI **does not yet have**:
  - A way to inspect a single run by id (status snapshot).
  - A way to filter `run list` by the experiment-tag column.
  - A way to discover or browse the experiment-tag namespace from the CLI.

PR 8 fills exactly those three gaps and nothing else.

## Target State For This PR

```bash
# Run lifecycle (additions only — existing commands unchanged)
ergon run status <run-id>                   # NEW — show single run status
ergon run list [--status=S] [--experiment=<tag>] [--limit=N]  # EXTENDED — adds --experiment

# Experiment-tag observation (additive — existing UUID-based commands unchanged)
ergon experiment tags                       # NEW — list distinct experiment-tag strings
ergon experiment by-tag <tag>               # NEW — list definitions in a tag, with latest run
```

That's the full new CLI surface.  All read-only against persisted state.  Existing commands — `experiment show <UUID>`, `experiment list`, `run list` (without --experiment), `run cancel` — keep working exactly as they do today.

## Task 1: Add Repository Helpers

**Files:**

- Modify: `ergon_core/ergon_core/core/application/experiments/repository.py`
- Modify: `ergon_core/ergon_core/core/application/workflows/runs.py`

The new CLI handlers need a few thin reads.  Add them next to the existing repository code, not as standalone abstractions.

- [ ] **Step 1: `DefinitionRepository.list_by_experiment_tag`**

  In `core/application/experiments/repository.py`, add a method that takes a session and an experiment tag string, and returns the matching `BenchmarkDefinitionRecord` rows.

  ```python
  def list_by_experiment_tag(
      self,
      session: Session,
      tag: str,
  ) -> list[BenchmarkDefinitionRecord]:
      """List ``BenchmarkDefinitionRecord`` rows tagged with ``tag``.

      The ``experiment`` column groups records into a named logical
      experiment; this helper is the read side of that grouping.
      """
      stmt = select(BenchmarkDefinitionRecord).where(
          BenchmarkDefinitionRecord.experiment == tag,
      )
      return list(session.exec(stmt).all())
  ```

- [ ] **Step 2: `DefinitionRepository.distinct_experiment_tags`**

  ```python
  def distinct_experiment_tags(self, session: Session) -> list[str]:
      """Distinct non-null ``experiment`` tag values across all records."""
      stmt = (
          select(BenchmarkDefinitionRecord.experiment)
          .where(BenchmarkDefinitionRecord.experiment.is_not(None))
          .distinct()
      )
      return [row for row in session.exec(stmt).all() if row is not None]
  ```

- [ ] **Step 3: `latest_run_for_definition` helper**

  In `core/application/workflows/runs.py`, add a module-level helper (matches the style of the existing `cancel_run` / `create_run` functions in that file):

  ```python
  def latest_run_for_definition(definition_id: UUID) -> RunRecord | None:
      """Most-recent ``RunRecord`` for a given workflow definition, or None."""
      with get_session() as session:
          stmt = (
              select(RunRecord)
              .where(RunRecord.workflow_definition_id == definition_id)
              .order_by(RunRecord.created_at.desc())
              .limit(1)
          )
          return session.exec(stmt).first()
  ```

  Note: this uses ``workflow_definition_id`` (the ``ExperimentDefinition`` FK), not ``experiment_id``.  The ``experiment_id`` column on ``RunRecord`` still exists but is being narrowed in PR 11.

## Task 2: Add `ergon run status` Command

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/run.py`

The existing `run.py` already has `list_runs` and `cancel_run` handlers and a `handle_run` dispatcher.  Add a third action.

- [ ] **Step 1: `status_run` handler**

  ```python
  def status_run(args: Namespace) -> int:
      ensure_db()
      try:
          run_id = UUID(args.run_id)
      except ValueError:
          print(f"Invalid UUID: {args.run_id}")
          return 1

      with get_session() as session:
          run = session.get(RunRecord, run_id)
          if run is None:
              print(f"No run found with id {args.run_id}")
              return 1

      print(f"run_id:                 {run.id}")
      print(f"status:                 {run.status}")
      print(f"benchmark_type:         {run.benchmark_type}")
      print(f"workflow_definition_id: {run.workflow_definition_id}")
      print(f"instance_key:           {run.instance_key}")
      if run.evaluator_slug is not None:
          print(f"evaluator:              {run.evaluator_slug}")
      if run.model_target is not None:
          print(f"model:                  {run.model_target}")
      created = run.created_at.strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "-"
      print(f"created_at:             {created}")
      if run.started_at:
          print(f"started_at:             {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
      if run.completed_at:
          print(f"completed_at:           {run.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
      if run.error_message:
          print(f"error:                  {run.error_message}")
      return 0
  ```

- [ ] **Step 2: Dispatch in `handle_run`**

  Update the existing `handle_run` dispatcher to route `status`:

  ```python
  def handle_run(args: Namespace) -> int:
      if args.run_action == "list":
          return list_runs(args)
      elif args.run_action == "cancel":
          return cancel_run(args)
      elif args.run_action == "status":
          return status_run(args)
      else:
          print("Usage: ergon run {list|status|cancel}")
          return 1
  ```

## Task 3: Add `--experiment` Filter to `ergon run list`

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/run.py`

The existing `list_runs` filters by `--status` and `--limit`.  Add an optional `--experiment=<tag>` filter that joins through `BenchmarkDefinitionRecord.experiment`.

- [ ] **Step 1: Extend `list_runs`**

  In `list_runs`, after the status filter, add the experiment-tag join:

  ```python
  if args.experiment:
      stmt = stmt.join(
          BenchmarkDefinitionRecord,
          RunRecord.experiment_id == BenchmarkDefinitionRecord.id,
      ).where(BenchmarkDefinitionRecord.experiment == args.experiment)
  ```

  The join is via `RunRecord.experiment_id` → `BenchmarkDefinitionRecord.id`.  This is the legacy FK from PR 6.5; PR 11 will narrow it.  Once narrowed, this filter will need to route through `ExperimentDefinition` / a tagging story — flag this in the PR 11 plan.

  Add the import at the top of the file:
  ```python
  from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord
  ```

- [ ] **Step 2: Update empty-result message**

  When no rows match, mention the filters that were in play:

  ```python
  if not runs:
      parts = ["No runs found"]
      if args.status:
          parts.append(f"with status={args.status!r}")
      if args.experiment:
          parts.append(f"for experiment={args.experiment!r}")
      print(" ".join(parts))
      return 0
  ```

## Task 4: Add `ergon experiment tags` + `experiment by-tag` Commands

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/experiment.py`

The existing `experiment.py` already has `handle_experiment_show` and `handle_experiment_list` (both UUID-based, both kept).  Add two new tag-namespace handlers.

- [ ] **Step 1: `handle_experiment_tags`**

  ```python
  def handle_experiment_tags(args: Namespace) -> int:
      _ensure_cli_logging()
      with get_session() as session:
          tags = DefinitionRepository().distinct_experiment_tags(session)
      if not tags:
          logger.info(
              "No experiment tags yet.  Tag definitions by setting "
              "`experiment` on the underlying record (cohort harness)."
          )
          return 0
      for tag in tags:
          logger.info("%s", tag)
      return 0
  ```

- [ ] **Step 2: `handle_experiment_by_tag`**

  ```python
  def handle_experiment_by_tag(args: Namespace) -> int:
      _ensure_cli_logging()
      with get_session() as session:
          records = DefinitionRepository().list_by_experiment_tag(
              session, args.tag,
          )
      if not records:
          logger.info("No definitions tagged with experiment=%r", args.tag)
          return 0
      logger.info("DEFINITION_ID\tNAME\tBENCHMARK\tSTATUS\tLATEST_RUN_STATUS")
      for record in records:
          latest = latest_run_for_definition(record.id)
          latest_status = latest.status if latest else "no runs"
          logger.info(
              "%s\t%s\t%s\t%s\t%s",
              record.id,
              record.name,
              record.benchmark_type,
              record.status,
              latest_status,
          )
      return 0
  ```

  Imports at the top of the file:

  ```python
  from ergon_core.core.application.experiments.repository import DefinitionRepository
  from ergon_core.core.application.workflows.runs import latest_run_for_definition
  from ergon_core.core.persistence.shared.db import get_session
  ```

- [ ] **Step 3: Dispatch in `handle_experiment`**

  Update the existing `handle_experiment` dispatcher:

  ```python
  async def handle_experiment(args: Namespace) -> int:
      _ensure_cli_logging()
      if args.experiment_action == "show":
          return handle_experiment_show(args)
      if args.experiment_action == "list":
          return handle_experiment_list(args)
      if args.experiment_action == "tags":
          return handle_experiment_tags(args)
      if args.experiment_action == "by-tag":
          return handle_experiment_by_tag(args)
      logger.error("Usage: ergon experiment {show|list|tags|by-tag}")
      return 1
  ```

## Task 5: Register Subparsers + Tests

**Files:**

- Modify: `ergon_cli/ergon_cli/main.py`
- Create: `ergon_cli/tests/unit/cli/test_run_cli.py`
- Modify: `ergon_cli/tests/unit/cli/test_experiment_cli.py`

- [ ] **Step 1: Register new `run` subcommand parsers in `main.py`**

  Find the existing `run` subparser block and add `status` and the `--experiment` flag on `list`:

  ```python
  run_status_parser = run_sub.add_parser("status", help="Show status of one run")
  run_status_parser.add_argument("run_id", help="Run ID (UUID)")

  # Extend the existing run_list_parser
  run_list_parser.add_argument(
      "--experiment",
      default=None,
      help="Filter by experiment tag (BenchmarkDefinitionRecord.experiment)",
  )
  ```

- [ ] **Step 2: Register new `experiment` subcommand parsers in `main.py`**

  Find the existing `experiment` subparser block and add `tags` and `by-tag`:

  ```python
  experiment_sub.add_parser("tags", help="List distinct experiment tags")
  experiment_by_tag_parser = experiment_sub.add_parser(
      "by-tag", help="List definitions for an experiment tag"
  )
  experiment_by_tag_parser.add_argument("tag", help="Experiment tag")
  ```

- [ ] **Step 3: Create `tests/unit/cli/test_run_cli.py`**

  Cover four cases.  Use the same pattern as `test_experiment_cli.py` (monkeypatched fakes, `Namespace` direct calls, `capsys`):

  - `test_run_status_prints_status_fields` — fake a `RunRecord` returned by `session.get`, assert key fields land in stdout.
  - `test_run_status_reports_invalid_uuid` — pass a non-UUID, assert exit code 1 and helpful message.
  - `test_run_status_reports_missing_run` — fake `session.get` returning `None`, assert exit code 1 and helpful message.
  - `test_run_list_filters_by_experiment` — wire a fake session whose `select(...).where(...).join(...).where(...).limit(...)` chain captures the call shape; assert the filter is applied.  (Alternatively: integration test against an in-memory SQLite session if the project already has a helper for that.)

- [ ] **Step 4: Extend `test_experiment_cli.py`**

  Add three cases:

  - `test_experiment_tags_lists_distinct_tags` — monkeypatch `DefinitionRepository` with `distinct_experiment_tags` returning a list; assert tags appear in `caplog.text`.
  - `test_experiment_tags_handles_empty` — monkeypatch returns `[]`; assert helpful empty-state message.
  - `test_experiment_by_tag_lists_definitions_with_latest_run_status` — monkeypatch `DefinitionRepository.list_by_experiment_tag` and `latest_run_for_definition` to return fakes; assert each definition and its latest run status appear.

  Also extend the existing parser test:

  ```python
  def test_experiment_subcommands_are_registered_in_main_parser() -> None:
      parser = build_parser()
      tags_args = parser.parse_args(["experiment", "tags"])
      by_tag_args = parser.parse_args(["experiment", "by-tag", "alpha"])
      assert tags_args.experiment_action == "tags"
      assert by_tag_args.experiment_action == "by-tag"
      assert by_tag_args.tag == "alpha"
  ```

- [ ] **Step 5: Run focused tests**

  ```bash
  uv run pytest ergon_cli/tests/unit/cli -q
  ```

  All green.

## Task 6: Documentation

**Files:**

- Modify: `docs/architecture/06_builtins.md` (the "Discovery" section added in PR 6.5)
- Modify: `ergon_builtins/ergon_builtins/benchmarks/README.md` (if present — cross-link to the new CLI commands)
- Modify: top-level `README.md` (if it documents CLI commands)

- [ ] **Step 1: Update the discovery section**

  In `06_builtins.md`, expand the observation section to mention:

  > After kicking off a run from Python, observe it via the CLI:
  > - `ergon run status <run-id>` — current state of one run
  > - `ergon run list [--status=S] [--experiment=<tag>]` — list runs, optionally filtered
  > - `ergon experiment show <UUID>` — full experiment detail (UUID-based)
  > - `ergon experiment list` — list recent experiments
  > - `ergon experiment tags` — list distinct experiment-tag strings
  > - `ergon experiment by-tag <tag>` — list definitions sharing a tag, with latest run status

- [ ] **Step 2: Update the catalogue README** (if it exists)

  Mirror the same six-bullet block.  If the file doesn't exist, skip — don't create one.

- [ ] **Step 3: Update top-level README**

  If the repo's `README.md` documents CLI commands, add the new ones; remove any references to deleted commands (PR 6.5 should have already cleaned those up).

## Task 7: Full Check Suite + Commit

- [ ] **Step 1: Backend checks**

  ```bash
  pnpm run check:be
  ```

- [ ] **Step 2: Backend tests**

  ```bash
  pnpm run test:be:fast
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add -A
  git commit -m "PR 8: lifecycle CLI commands (run status, --experiment filter, experiment tags/by-tag)

  - Add ergon run status <run-id>
  - Add --experiment filter to ergon run list
  - Add ergon experiment tags + experiment by-tag <tag>
  - Add repository helpers (distinct_experiment_tags, list_by_experiment_tag,
    latest_run_for_definition)
  - Documentation updates pointing users at the new observation commands

  No authoring path on the CLI; Python remains the only way to start a run."
  ```

## Verification

- All `pnpm run check:be` steps green.
- All `pnpm run test:be:fast` tests pass (including new CLI tests).
- `ergon run status <run-id>` returns expected status for a known run.
- `ergon experiment tags` returns the set of distinct tag strings.
- `ergon experiment by-tag <tag>` returns definitions tagged with that string and their latest-run status.

## What This PR Is NOT

- **Not an authoring path.**  No `ergon experiment define`, no `ergon run <benchmark>`, no benchmark / worker registry dicts.  Authoring is Python-only (PR 6.5 made this decision).
- **Not a new abstraction layer.**  These commands are thin wrappers around existing repositories — no DTOs, no service classes, no factory registries.
- **Not a replacement of `experiment show <UUID>` / `experiment list`.**  Those PR-6.5 commands stay.  The new `tags` / `by-tag` commands are *additive* — they surface the experiment-tag namespace (`BenchmarkDefinitionRecord.experiment`) which the UUID-based commands don't expose.
- **Not a dashboard replacement.**  CLI commands are for quick terminal-driven observation.  Rich UI lives in the dashboard.
- **Not a change to `persist_benchmark` or `launch_run`.**  Those are stable after PR 6.5 / 7.
- **Not a `Benchmark(experiment=...)` constructor kwarg.**  Tagging is still write-side-only today; PR 8 only adds *read* commands.  A constructor kwarg can be added later if needed.

## Risks

- **`RunRecord.experiment_id` is being narrowed in PR 11.**  Today the `run list --experiment=<tag>` filter joins via `RunRecord.experiment_id → BenchmarkDefinitionRecord.id`.  PR 11 will narrow that FK; the filter logic will need to follow.  *Mitigation:* call this out in the PR 11 plan as a CLI follow-up.
- **Tag concept is half-wired.**  The `experiment` column is populated by the cohort / test harness today but not by the public authoring API.  Until a `Benchmark(experiment=...)` kwarg lands, users coming through `persist_benchmark` won't have anything to query.  *Mitigation:* empty-state messages on the new commands point at the cohort harness as the only path to a tag today.
- **`cancel_run` is sync, but `handle_experiment` is async.**  The CLI's argparse dispatch already handles a mix of sync and async handlers (see `main.py`).  No change needed.

## PR Ledger

- **Invariant landed:** the CLI is observation-only; authoring is Python-only.
- **Bridge code introduced:** none.
- **Old paths still alive:** `RunRecord.experiment_id` (gated for PR 11); `BenchmarkDefinitionRecord` table (gated for PR 11).
- **Deletion gate:** none new from this PR.
- **Tests added or updated:** `test_run_cli.py` (new), `test_experiment_cli.py` (extended).
- **Modules owned by this PR:** `ergon_cli/commands/run.py` (extended), `ergon_cli/commands/experiment.py` (extended), repository helpers in `ergon_core/core/application/experiments/repository.py` and `ergon_core/core/application/workflows/runs.py`.
