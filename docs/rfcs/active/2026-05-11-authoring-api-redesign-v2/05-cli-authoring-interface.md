# 05 — CLI authoring interface

> What `ergon define` and `ergon run` actually do, after the v1
> divergence is repaired. The short answer: the CLI is a composition
> convenience, not a parallel persistence path. It builds an `Experiment`
> from a registered factory and calls the same `persist_definition`
> entry point the public Python API uses. There is no second slug-based
> persistence flow.
>
> See [`01-api-surface.md`](01-api-surface.md) for the public types,
> [`02-persistence-layer.md`](02-persistence-layer.md) for the
> persistence model, and
> [`../2026-05-08-authoring-api-redesign/08-cleanup-audit.md`](../2026-05-08-authoring-api-redesign/08-cleanup-audit.md)
> for the v1 audit finding that motivated this doc.

## Why this doc exists

v1 grew two parallel ways to persist an experiment definition:

- **Public Python API.** Author writes a benchmark factory, constructs
  `Experiment(benchmark=..., ...)`, calls
  `persist_definition(experiment)`. Hits
  `experiment_definitions` + `experiment_definition_tasks` +
  `experiment_definition_edges`. Used by the dashboard, by tests, and by
  any agent that wants to programmatically launch a run.
- **CLI slug path.** `ergon define <benchmark-slug>` resolved a slug
  through `ergon_builtins.benchmarks._registry`, called a
  `_persist_single_sample_workflow_definition` helper, wrote rows into a
  `saved_specs` table that **no other code in the system reads**. Used
  by no one in production; tested only by tests of the CLI command
  itself.

The CLI path was non-functional in the literal sense: a definition
written by the CLI could not be launched as a run, because the launcher
reads from `experiment_definitions`, not from `saved_specs`. The v1
audit categorized `saved_specs` as write-only dead infrastructure and
the CLI define path as a parallel non-functional code branch.

v2 unifies. The CLI **builds** an `Experiment` and **delegates** to the
public persistence path. There is one persistence flow.

## Architectural model

```
                 ┌─ public Python API path ──────────────────────────┐
                 │                                                   │
author code ─►   Experiment(...) ─►  persist_definition(experiment) ─►
                                                                     │
                                                                     ▼
                                            experiment_definitions
                                            + experiment_definition_tasks
                                            + experiment_definition_edges
                                                                     ▲
                                                                     │
                ┌─ CLI path ─────────────────────────────────────────┤
                │                                                    │
$ ergon define <slug>  ─►  _BUILTIN_BENCHMARKS[slug]() ─►            │
                              build Experiment(...) ─►               │
                                  persist_definition(experiment) ────┘
```

There is one persistence implementation. The CLI is a convenience that
selects which `Experiment` to build via a slug.

## CLI entry points

### `ergon define <benchmark-slug> [--name NAME] [--description TEXT]`

What it does:

1. Resolve `<benchmark-slug>` to a benchmark factory:
   ```python
   _BUILTIN_BENCHMARKS: dict[str, Callable[[], Benchmark]] = {
       "minif2f-react-baseline": lambda: MiniF2FBenchmark(...),
       "swebench-react-baseline": lambda: SWEBenchBenchmark(...),
       # ...
   }
   ```
   Static dict in `ergon_builtins`, no dynamic lookup, no registry
   table. The slug is purely a CLI ergonomics aid.
2. Build a `Benchmark` instance by calling the factory.
3. Wrap it in an `Experiment`:
   ```python
   experiment = Experiment(
       benchmark=benchmark,
       name=name or f"{slug}-{datetime.utcnow().isoformat()}",
       description=description,
       metadata={"created_by": "cli", "slug": slug},
   )
   ```
4. Call the same `persist_definition(experiment)` the public Python API
   uses.
5. Print the new `definition_id` so the user can `ergon run
   <definition_id>` next.

```python
# Inside ergon_cli.commands.define — full implementation:
def define(
    slug: str,
    *, name: str | None = None, description: str | None = None,
) -> None:
    factory = _BUILTIN_BENCHMARKS.get(slug)
    if factory is None:
        raise typer.BadParameter(
            f"Unknown benchmark slug: {slug!r}. "
            f"Known slugs: {sorted(_BUILTIN_BENCHMARKS)}"
        )

    experiment = Experiment(
        benchmark=factory(),
        name=name or _default_name(slug),
        description=description,
        metadata={"created_by": "cli", "slug": slug},
    )
    handle = persist_definition(experiment)
    typer.echo(f"defined {handle.definition_id}")
```

That's the entire CLI define command. **No `_persist_single_sample_workflow_definition`,
no `saved_specs` writes, no second resolution path.**

### `ergon run <definition-id> [--metadata KEY=VALUE]...`

What it does:

1. Take a `definition_id` (UUID) — the same id `ergon define` printed.
   This is the only handle a run needs; benchmark slugs are *not* a
   valid input here. (Rationale: a slug-input run would re-resolve the
   factory and could pick up different code than was persisted; pinning
   to `definition_id` means runs always execute the exact persisted
   payload.)
2. Call `launch_run(definition_id, run_metadata=...)` — the same entry
   point the public Python API uses.
3. Print the new `run_id` so the user can stream logs / poll status.

```python
def run(
    definition_id: UUID,
    *, metadata: list[str] = (),
) -> None:
    run_metadata = dict(_parse_kv(item) for item in metadata)
    handle = launch_run(definition_id, metadata=run_metadata)
    typer.echo(f"launched run {handle.run_id} (definition {definition_id})")
```

### No `ergon run <slug>` shortcut `[v2: locked out]`

The "define and run in one step" shortcut is deliberately *not*
provided. `ergon run` accepts a `definition_id` (UUID) only.

Rationale: shortcuts that conflate define and run muddy the mental
model — users start to think "running a slug" is one operation when it
is actually two (a write to `experiment_definitions` followed by a
write to `runs`). Two-step is honest about what happened: the slug
*became* a definition, and the definition *became* a run. The two-line
shell invocation `defn=$(ergon define <slug>) && ergon run "$defn"` is
the canonical compose pattern.

## What CLI does *not* do

### No second persistence path

There is no `saved_specs` table, no
`_persist_single_sample_workflow_definition` helper, no
`SavedSpecRepository`. The v1 audit identified these as write-only
dead infrastructure. Deletion lives in
[`09-implementation-plan.md`](09-implementation-plan.md).

### No slug-based registry table in the database

The `BUILTIN_BENCHMARKS` dict in `ergon_builtins` is **in-process
Python state**, not a database table. The slug is a CLI argument and
nothing else; it does not survive into `experiment_definitions` as a
foreign key (it goes into `metadata.slug` as a free-form string for
human reference only).

This means: third-party benchmark packages don't register slugs
through a database insert. They ship their own CLI plugin that
contributes to a different `BUILTIN_BENCHMARKS`-shaped dict, or users
build their `Experiment` programmatically and skip the slug entirely.

### No CLI-side validation

`Experiment.@model_validator(mode="after")` already enforces
`requires_sandbox` compatibility at construction time
([01-api-surface.md "Foundational change C"](01-api-surface.md#foundational-change-c--experiment-lifts-into-the-public-api)).
`ExperimentValidationService` already enforces cross-component rules
during `persist_definition`. The CLI does not duplicate either. A
malformed slug factory raises at `factory()` call time; the user sees
the original Python error, not a wrapped CLI error.

## Composition convenience, not abstraction

The slug system in v2 is *deliberately* unfancy:

- It's a `dict[str, Callable[[], Benchmark]]`.
- It lives in one Python module (`ergon_builtins.benchmarks._registry`).
- It is mutated only by being edited.
- It is not pluggable across packages without users editing the dict.

If a user wants more than this — e.g. "every benchmark in my private
package shows up in `ergon define --list`" — they import their
benchmark module and call `persist_definition(...)` directly. The CLI
is for the in-tree benchmark catalogue only.

This design is reachable from "the CLI was non-functional" because the
non-functionality came from the CLI doing *too much*: it tried to be a
parallel persistence interface with its own resolution semantics. v2's
CLI does *less*, which is why it works.

## Testing

The architecture-guard test in
[`07-test-strategy.md`](07-test-strategy.md) enforces:

```python
def test_no_saved_specs_imports() -> None:
    """ergon_core, ergon_cli, ergon_builtins must not import any
    `saved_specs` symbol — the package is deleted as of v2."""

def test_cli_define_routes_through_persist_definition() -> None:
    """ergon_cli.commands.define must call persist_definition, not
    any helper named *_persist_single_sample_workflow_definition*
    (deleted) or any saved-specs write path (deleted)."""
```

The CLI's own behavioural test asserts that after `ergon define
<slug>`, the new `definition_id` is loadable by `launch_run` —
catching any regression that re-introduces a parallel persistence
path.

## Decisions locked at workshop `[v2: locked]`

- **Plugin slug registration** — **locked: deferred.** Third-party
  packages don't register slugs through any framework hook. They call
  `persist_definition(experiment)` directly. The CLI is for in-tree
  benchmarks only.
- **`ergon run --override`** — **locked: not allowed.** Overrides
  always produce a fresh `experiment_definitions` row via a new
  `ergon define`. `definition_id` is 1:1 with what was actually
  executed; no exceptions.
- **Cohort runs from CLI** — **locked: deferred.** v2 ships
  one-run-per-invocation. `--replicas N` is a follow-up if a real
  workload demands it.
- **`ergon launch <slug>` convenience** — **locked out: rejected.**
  Per "No `ergon run <slug>` shortcut" above; explicit two-step
  preserves the mental model.
