# PR 8 — Lifecycle CLI Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Add the lifecycle / observation commands the CLI keeps after PR 6.5 killed the authoring route.  No new abstractions.  No factory dispatch.  No per-benchmark CLI registration burden.

**Context:** PR 6.5 made the call (and recorded the rationale in `docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md`) that the CLI has **exactly one role**: lifecycle and observation of persisted state.  Authoring is Python-only.  PR 6.5 deleted the existing `ergon experiment define` / `ergon experiment run` commands.  PR 8 adds the replacement commands users need to *observe* and *manage* what's already running.

**Scope (much smaller than the original plan):** five new commands.  Each is a thin wrapper around an existing repository read.  No DTOs, no factory registries, no new abstractions.

**Tech Stack:** argparse CLI handlers, existing repositories (`RunRepository`, `DefinitionRepository`), pytest CLI tests.

---

## Files

**Create:**

```text
ergon_cli/ergon_cli/commands/run.py             # run status / cancel / list
ergon_cli/tests/unit/cli/test_run_cli.py        # tests for the new commands
```

**Modify:**

```text
ergon_cli/ergon_cli/commands/experiment.py      # add show + list, after PR 6.5 deleted define/run
ergon_cli/ergon_cli/__main__.py                 # register new subparsers
ergon_cli/tests/unit/cli/test_experiment_cli.py # tests for show + list
ergon_core/ergon_core/core/persistence/telemetry/repository.py  # add small repo methods if needed (list_by_experiment, distinct_experiments)
```

## Current State (after PR 6.5)

After PR 6.5 lands:

- The public `Experiment` wrapper class is gone (PR 6.5).
- `persist_benchmark(benchmark) -> DefinitionHandle` is the authoring API
  (module-level function in `ergon_core.api`). Identity fields (``name``,
  ``description``, ``metadata``) are read off the ``Benchmark`` instance
  directly — no kwargs.
- `BenchmarkDefinitionRecord` is the persisted row, with an `experiment: str | None` column.
- The CLI has no `experiment define` / `experiment run` / `run <benchmark>` commands — those were deleted.
- **Note on the `experiment` tag:** the `BenchmarkDefinitionRecord.experiment`
  column exists for grouping definitions under a named experiment, but
  there is **no `experiment` kwarg on `persist_benchmark`** today. Tagging
  is currently a write-side-only column populated by the test harness;
  if PR 8 needs CLI-driven tagging, this PR must add a wiring path (most
  naturally a `Benchmark(experiment=...)` constructor kwarg matching the
  `name`/`description`/`metadata` shape).
- The CLI has `experiment` and `run` top-level subcommand groups registered but mostly empty after PR 6.5.

Users currently kick off runs from Python.  They have no CLI way to check status or cancel.  This PR fills that gap.

## Target State For This PR

```bash
# Run lifecycle
ergon run status <run-id>            # print status of one run
ergon run cancel <run-id>            # cancel a running run
ergon run list [--experiment=<tag>]  # list runs, optionally filtered by experiment tag

# Experiment (string tag) queries
ergon experiment show <name>         # list definitions tagged with this experiment
ergon experiment list                # list distinct experiment tags in the database
```

That's the full new CLI surface.  All read-only against persisted state, except `cancel` which sends a cancel event to the existing cancellation machinery.

## Task 1: Add Repository Helpers (If Missing)

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/telemetry/repositories.py`

The CLI handlers need a few repository methods that may not exist yet.  Add them as thin wrappers around existing SQLModel queries.

- [ ] **Step 1: `DefinitionRepository.list_by_experiment`**

  ```python
  def list_by_experiment(self, experiment: str) -> list[BenchmarkDefinitionRecord]:
      """List all definitions tagged with the given experiment string."""
      with self._session() as session:
          stmt = select(BenchmarkDefinitionRecord).where(
              BenchmarkDefinitionRecord.experiment == experiment
          )
          return list(session.exec(stmt).all())
  ```

- [ ] **Step 2: `DefinitionRepository.distinct_experiments`**

  ```python
  def distinct_experiments(self) -> list[str]:
      """List distinct non-null experiment tags."""
      with self._session() as session:
          stmt = select(BenchmarkDefinitionRecord.experiment).distinct().where(
              BenchmarkDefinitionRecord.experiment.is_not(None)
          )
          return [row for row in session.exec(stmt).all() if row is not None]
  ```

- [ ] **Step 3: `RunRepository.list` filter**

  Confirm `RunRepository.list()` accepts an optional `experiment: str | None` filter (joining through the definition table).  If not, add it:

  ```python
  def list(self, *, experiment: str | None = None) -> list[RunRecord]:
      """List runs, optionally filtered by experiment tag (joins via definition)."""
      with self._session() as session:
          stmt = select(RunRecord)
          if experiment is not None:
              stmt = stmt.join(BenchmarkDefinitionRecord).where(
                  BenchmarkDefinitionRecord.experiment == experiment
              )
          return list(session.exec(stmt).all())
  ```

- [ ] **Step 4: `RunRepository.latest_for_definition`**

  ```python
  def latest_for_definition(self, definition_id: UUID) -> RunRecord | None:
      """Return the most-recent run for this definition, if any."""
      with self._session() as session:
          stmt = (
              select(RunRecord)
              .where(RunRecord.definition_id == definition_id)
              .order_by(RunRecord.created_at.desc())
              .limit(1)
          )
          return session.exec(stmt).first()
  ```

- [ ] **Step 5: Cancel helper**

  Confirm `cancel_run(run_id: UUID, *, reason: str) -> None` exists in the application layer.  If not, locate where cancellation logic lives today (likely `core/application/runs/...`) and surface a thin function for the CLI to call.

## Task 2: Add `ergon run` Subcommands

**Files:**

- Create: `ergon_cli/ergon_cli/commands/run.py`

- [ ] **Step 1: `handle_run_status`**

  ```python
  from argparse import Namespace
  from uuid import UUID

  from ergon_core.core.application.runs.cancel import cancel_run
  from ergon_core.core.persistence.telemetry.repositories import (
      DefinitionRepository,
      RunRepository,
  )


  def handle_run_status(args: Namespace) -> int:
      _ensure_cli_logging()
      ensure_db()
      run = RunRepository().get(UUID(args.run_id))
      if run is None:
          print(f"No run found with id {args.run_id}")
          return 1
      print(f"run_id:    {run.run_id}")
      print(f"status:    {run.status}")
      print(f"created:   {run.created_at}")
      print(f"definition: {run.definition_id}")
      return 0
  ```

  (Counts like `tasks_completed/total` are nice-to-have; keep the first cut minimal.  Expand once the basic command works.)

- [ ] **Step 2: `handle_run_cancel`**

  ```python
  async def handle_run_cancel(args: Namespace) -> int:
      _ensure_cli_logging()
      ensure_db()
      await cancel_run(UUID(args.run_id), reason=args.reason or "cli-cancel")
      print(f"cancelled run {args.run_id}")
      return 0
  ```

- [ ] **Step 3: `handle_run_list`**

  ```python
  def handle_run_list(args: Namespace) -> int:
      _ensure_cli_logging()
      ensure_db()
      runs = RunRepository().list(experiment=args.experiment)
      if not runs:
          msg = "No runs found"
          if args.experiment:
              msg += f" for experiment={args.experiment!r}"
          print(msg)
          return 0
      for r in runs:
          print(f"{r.run_id}  {r.status:12s}  {r.definition_id}")
      return 0
  ```

## Task 3: Add `ergon experiment` Subcommands

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/experiment.py`

After PR 6.5 deleted `handle_experiment_define` / `handle_experiment_run`, this file is mostly empty (or gone — if PR 6.5 deleted the file entirely, recreate it here).

- [ ] **Step 1: `handle_experiment_show`**

  ```python
  def handle_experiment_show(args: Namespace) -> int:
      _ensure_cli_logging()
      ensure_db()
      defs = DefinitionRepository().list_by_experiment(args.experiment_name)
      if not defs:
          print(f"No definitions found for experiment={args.experiment_name!r}")
          return 0
      run_repo = RunRepository()
      for d in defs:
          latest = run_repo.latest_for_definition(d.definition_id)
          status = latest.status if latest else "no runs"
          print(f"{d.name:30s}  {d.definition_id}  {status}")
      return 0
  ```

- [ ] **Step 2: `handle_experiment_list`**

  ```python
  def handle_experiment_list(args: Namespace) -> int:
      _ensure_cli_logging()
      ensure_db()
      names = DefinitionRepository().distinct_experiments()
      if not names:
          print(
              "No experiments yet.  Tag definitions by setting "
              "`experiment` on the Benchmark (or via the cohort harness)."
          )
          return 0
      for n in names:
          print(n)
      return 0
  ```

## Task 4: Register Subparsers

**Files:**

- Modify: `ergon_cli/ergon_cli/__main__.py` (or wherever the argparse tree is built)

- [ ] **Step 1: `ergon run` group**

  Confirm `ergon run` exists as a top-level subcommand group.  If PR 6.5 deleted it along with `experiment run`, recreate it.

  ```python
  run_parser = subparsers.add_parser("run", help="run lifecycle commands")
  run_subparsers = run_parser.add_subparsers(dest="run_cmd", required=True)

  status_p = run_subparsers.add_parser("status", help="show run status")
  status_p.add_argument("run_id")
  status_p.set_defaults(func=handle_run_status)

  cancel_p = run_subparsers.add_parser("cancel", help="cancel a running run")
  cancel_p.add_argument("run_id")
  cancel_p.add_argument("--reason", default=None)
  cancel_p.set_defaults(func=handle_run_cancel)

  list_p = run_subparsers.add_parser("list", help="list runs")
  list_p.add_argument("--experiment", default=None, help="filter by experiment tag")
  list_p.set_defaults(func=handle_run_list)
  ```

- [ ] **Step 2: `ergon experiment` group**

  ```python
  experiment_parser = subparsers.add_parser("experiment", help="experiment-tag queries")
  experiment_subparsers = experiment_parser.add_subparsers(dest="experiment_cmd", required=True)

  show_p = experiment_subparsers.add_parser("show", help="show definitions in an experiment")
  show_p.add_argument("experiment_name")
  show_p.set_defaults(func=handle_experiment_show)

  list_p2 = experiment_subparsers.add_parser("list", help="list known experiment tags")
  list_p2.set_defaults(func=handle_experiment_list)
  ```

## Task 5: Tests

**Files:**

- Create: `ergon_cli/tests/unit/cli/test_run_cli.py`
- Modify: `ergon_cli/tests/unit/cli/test_experiment_cli.py` (add the new commands; PR 6.5 deleted the old test cases for `define`/`run`)

- [ ] **Step 1: `test_run_status_prints_status` (monkeypatch the repo)**

  ```python
  def test_run_status_prints_status(monkeypatch, capsys):
      fake = RunRecord(run_id=uuid4(), status="running", definition_id=uuid4(), created_at=datetime.utcnow())
      monkeypatch.setattr(
          "ergon_cli.commands.run.RunRepository",
          lambda: SimpleNamespace(get=lambda _: fake),
      )
      result = handle_run_status(Namespace(run_id=str(fake.run_id)))
      out = capsys.readouterr().out
      assert result == 0
      assert "status:    running" in out
  ```

- [ ] **Step 2: `test_run_cancel_calls_cancel_run`**

  ```python
  @pytest.mark.asyncio
  async def test_run_cancel_calls_cancel_run(monkeypatch):
      called = {}
      async def fake_cancel(run_id, *, reason):
          called["run_id"] = run_id
          called["reason"] = reason
      monkeypatch.setattr("ergon_cli.commands.run.cancel_run", fake_cancel)
      result = await handle_run_cancel(Namespace(run_id=str(uuid4()), reason=None))
      assert result == 0
      assert called["reason"] == "cli-cancel"
  ```

- [ ] **Step 3: `test_run_list_filters_by_experiment`**

  ```python
  def test_run_list_filters_by_experiment(monkeypatch, capsys):
      calls = {}
      def fake_list(*, experiment):
          calls["experiment"] = experiment
          return []
      monkeypatch.setattr(
          "ergon_cli.commands.run.RunRepository",
          lambda: SimpleNamespace(list=fake_list),
      )
      handle_run_list(Namespace(experiment="ablation-x"))
      assert calls["experiment"] == "ablation-x"
  ```

- [ ] **Step 4: `test_experiment_show_lists_definitions`**

  ```python
  def test_experiment_show_lists_definitions(monkeypatch, capsys):
      fake_defs = [
          BenchmarkDefinitionRecord(definition_id=uuid4(), name="def-a", experiment="x"),
          BenchmarkDefinitionRecord(definition_id=uuid4(), name="def-b", experiment="x"),
      ]
      monkeypatch.setattr(
          "ergon_cli.commands.experiment.DefinitionRepository",
          lambda: SimpleNamespace(list_by_experiment=lambda name: fake_defs),
      )
      monkeypatch.setattr(
          "ergon_cli.commands.experiment.RunRepository",
          lambda: SimpleNamespace(latest_for_definition=lambda _: None),
      )
      result = handle_experiment_show(Namespace(experiment_name="x"))
      out = capsys.readouterr().out
      assert result == 0
      assert "def-a" in out and "def-b" in out
  ```

- [ ] **Step 5: `test_experiment_list_lists_distinct_tags`**

  ```python
  def test_experiment_list_lists_distinct_tags(monkeypatch, capsys):
      monkeypatch.setattr(
          "ergon_cli.commands.experiment.DefinitionRepository",
          lambda: SimpleNamespace(distinct_experiments=lambda: ["ablation-1", "ablation-2"]),
      )
      result = handle_experiment_list(Namespace())
      out = capsys.readouterr().out
      assert result == 0
      assert "ablation-1" in out and "ablation-2" in out
  ```

- [ ] **Step 6: Run focused tests**

  ```bash
  uv run pytest ergon_cli/tests/unit/cli -q
  ```

  All green.

## Task 6: Documentation

**Files:**

- Modify: `docs/architecture/06_builtins.md` (the "Discovery" section added in PR 6.5)
- Modify: `ergon_builtins/ergon_builtins/benchmarks/README.md` (cross-link to the new CLI commands)
- Modify: top-level `README.md` (if it documents CLI commands)

- [ ] **Step 1: Update the discovery section**

  In `06_builtins.md`, expand the "Discovery" section to mention that observation also happens via `ergon experiment list` and `ergon experiment show <name>`.

- [ ] **Step 2: Update the catalogue README**

  In `ergon_builtins/benchmarks/README.md`, add a "Once running" sub-section:

  > After kicking off a run from Python, observe it via the CLI:
  > - `ergon run status <run-id>` — current state of one run
  > - `ergon experiment show <name>` — definitions in an experiment, with run status
  > - `ergon experiment list` — known experiment tags

- [ ] **Step 3: Update top-level README**

  If the repo's `README.md` documents CLI commands, add the new ones; remove any references to the deleted `experiment define` / `experiment run` / `run <benchmark>` commands (PR 6.5 should have removed them; double-check).

## Task 7: Full Check Suite

- [ ] **Step 1: Backend checks**

  ```bash
  pnpm run check:be
  ```

- [ ] **Step 2: Backend tests**

  ```bash
  pnpm run test:be:fast
  ```

- [ ] **Step 3: Manual smoke**

  ```bash
  # Kick off a run from Python (one-liner; assumes a benchmark exists)
  uv run python -c "
  import asyncio
  from ergon_builtins.benchmarks.minif2f import MiniF2FBenchmark, make_minif2f_worker
  from ergon_core.api import persist_benchmark, launch_run

  async def main():
      b = MiniF2FBenchmark(
          name='smoke',
          metadata={'experiment': 'smoke-test'},
          worker_factory=make_minif2f_worker,
          limit=1,
      )
      h = persist_benchmark(b)
      print(f'DEFINITION_ID={h.definition_id}')
      await launch_run(h.definition_id)

  asyncio.run(main())
  "

  # Then observe via CLI
  ergon experiment list                  # should show 'smoke-test'
  ergon experiment show smoke-test       # should show the smoke definition
  ergon run list --experiment=smoke-test # should show the run
  ergon run status <run-id>              # status of the run
  ```

  Confirm each CLI command produces sensible output.

## Task 8: Commit

```bash
git add -A
git commit -m "PR 8: lifecycle CLI commands (run + experiment subcommands)

- Add ergon run status/cancel/list
- Add ergon experiment show/list
- Add repository helpers (list_by_experiment, distinct_experiments, latest_for_definition)
- Documentation updates to point users at the new observation commands

No authoring path on the CLI; Python remains the only way to start a run."
```

## Verification

- All `pnpm run check:be` steps green.
- All `pnpm run test:be:fast` tests pass (including new CLI tests).
- Manual smoke (Task 7 Step 3) succeeds end-to-end.
- `ergon experiment list` returns expected tags after definitions are persisted (the experiment tag is currently sourced via `Benchmark(metadata={"experiment": ...})` and read from `BenchmarkDefinitionRecord.experiment`; PR 8 may add a first-class `Benchmark(experiment=...)` kwarg).
- `ergon run status <run-id>` returns expected status for a known run.

## What This PR Is NOT

- **Not an authoring path.**  No `ergon experiment define`, no `ergon run <benchmark>`, no benchmark / worker registry dicts.  Authoring is Python-only (PR 6.5 made this decision).
- **Not a new abstraction layer.**  These commands are thin wrappers around existing repositories — no DTOs, no service classes, no factory registries.
- **Not a dashboard replacement.**  CLI commands are for quick terminal-driven observation.  Rich UI lives in the dashboard.
- **Not a change to `persist_benchmark` or `launch_run`.**  Those are stable after PR 6.5.

## Risks

- **Repository method signatures may need adjustment.**  If existing repos don't expose `get(uuid)` or `list_by_experiment`, Task 1 adds them.  Risk: stepping on a naming collision with a different method that already exists.  *Mitigation:* `rg "def list_by_experiment\|def distinct_experiments"` before adding.
- **Async cancel ergonomics.**  `cancel_run` is async, so `handle_run_cancel` is async too.  argparse dispatch needs to handle async handlers — confirm the existing argparse runner does this (it should, since `launch_run` was already async).  *Mitigation:* if not, wrap in `asyncio.run(...)` at the dispatch boundary.
- **`experiment` filter on `RunRepository.list` is a join.**  If the existing repo doesn't already join through definitions for filters, adding the join is more invasive than this plan suggests.  *Mitigation:* if the join is awkward, do the filter in two queries (list distinct definitions by experiment, then list runs for each).
- **Dashboard parity.**  The dashboard already has its own experiment-list / run-status views.  Risk: CLI output drifts from dashboard semantics.  *Mitigation:* both read from the same repo methods; if outputs diverge, the repo is the source of truth.

## PR Ledger

- **Invariant landed:** the CLI is observation-only; authoring is Python-only.
- **Bridge code introduced:** none.
- **Old paths still alive:** none — PR 6.5 removed the authoring CLI commands; PR 8 only adds observation commands.
- **Deletion gate:** none — these commands stay.
- **Tests added or updated:** `test_run_cli.py` (new), `test_experiment_cli.py` (rewritten for show/list).
- **Modules owned by this PR:** `ergon_cli/commands/run.py` (new), `ergon_cli/commands/experiment.py` (rewritten).
