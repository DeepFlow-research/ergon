# CLI Domain Standardization Program Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `ergon_cli` from a flat command bag into a clean inbound adapter
with typed domain boundaries, while relocating agent-facing dynamic authoring to
`ergon_builtins`.

**Architecture:** Land guardrail and ownership fixes first, then split parser
composition, introduce shared command/result contracts, move persistence-backed
commands behind services, move benchmark/onboarding metadata ownership, and
finish by deleting compatibility packages. Every PR must be runnable after
merge.

**Tech Stack:** Python 3.11+, argparse, Pydantic v2, SQLModel, pytest, ruff,
`ergon_core.api`, `ergon_builtins` toolkits.

---

## Required Base

This CLI refactor stack must branch from the landed contents of
[DeepFlow-research/ergon#91](https://github.com/DeepFlow-research/ergon/pull/91)
(`codex/core-refactor-pr12-final-architecture-gates`) or a later mainline commit
that contains that PR.

That base matters because PR #91 finalizes the core package shape and
architecture guards:

- `ergon_core.core.application.read_models` is retired.
- dashboard/API read DTOs and read services live under `ergon_core.core.views`.
- runtime graph/task/run services live under `ergon_core.core.application.runtime`.
- job contract DTOs are re-export-only boundaries; new CLI work must not depend
  on job-local `contract.py` files for application behavior.

If an implementation worktree is based on an older detached core-refactor branch,
rebase the CLI stack onto PR #91 before opening PR 00. Do not update this stack
against the older `application/read_models`, `application/graph`,
`application/tasks`, or `application/workflows` package layout.

## Why This Program Exists

The current CLI works, but it mixes unrelated roles:

- human/operator lifecycle commands
- stale static discovery catalogues
- direct persistence reads
- benchmark setup path knowledge
- onboarding dependency metadata
- agent-facing workflow tooling
- a half-retired dynamic task authoring surface

The target architecture treats `ergon_cli` as a terminal inbound adapter.
Authoring remains Python-first through `ergon_core.api`; agent-facing tools live
in `ergon_builtins`.

## Churn Budget

| Area | Likely churn |
| --- | ---: |
| CLI hygiene and tests | 500-1.2k changed lines |
| Builtins workflow toolkit ownership | 800-1.8k changed lines |
| Parser/domain folder split | 1k-2k changed lines |
| Shared output/errors/models | 800-1.5k changed lines |
| Runs/experiments boundary | 800-1.5k changed lines |
| Benchmarks/onboarding metadata | 1k-2k changed lines |
| Final migration/deletion guards | 500-1k changed lines |

PRs above 2.5k non-generated changed lines should split unless the excess is
mechanical file moves or deletion.

## Ownership Lanes

| Lane | Owns | Must Not Own |
| --- | --- | --- |
| `ergon_core.api` | Public authoring models, `WorkerContext.spawn_task`, runtime facades | CLI grammar, builtins UX |
| `ergon_builtins` | Benchmark/toolkit metadata, agent-facing tools, toy integration fixtures | Human/operator CLI implementation |
| `ergon_cli` | Terminal parsing, typed command translation, rendering, operator lifecycle commands | Dynamic task authoring, direct DB ownership, benchmark truth |
| Core application services | Runtime reads/mutations, graph rules, persistence boundaries | Argparse, printing |
| Tests | Architecture guards, CLI parser/output tests, builtins integration tests | Production adapters |

## Bridge Ledger

| Bridge | Introduced | New Default | Deleted |
| --- | --- | --- | --- |
| Static CLI discovery rows | Existing | PR 05 metadata catalogue | PR 06 |
| `ergon_cli.commands.*` compatibility imports | Existing | PR 02 domain parsers, PR 03+ domain commands | PR 06 |
| Builtins importing `ergon_cli.commands.workflow` | Existing | PR 01 builtins adapter | PR 01 |
| CLI workflow live authoring facade | Existing | PR 01 rejects/relocates | PR 01 |
| Direct persistence imports in CLI run/experiment commands | Existing | PR 04 CLI services/core views/runtime services | PR 04 |
| Hardcoded benchmark template paths in CLI | Existing | PR 05 builtins metadata | PR 05/06 |

## PR Sequence

| PR | Name | Runnable After Merge | Primary Invariant |
| ---: | --- | --- | --- |
| 00 | CLI hygiene cleanup | yes | No obvious no-op/stale CLI behavior remains |
| 01 | Dynamic subtask toolkit ownership | yes | Agent dynamic authoring is builtins over `WorkerContext`, not CLI |
| 02 | CLI composition root and parser split | yes | `main.py` is a boring entrypoint |
| 03 | Shared output/errors/command models | yes | Converted domains stop leaking `Namespace` below commands |
| 04 | Runs/experiments service boundary | yes | CLI no longer owns direct persistence reads for run/experiment commands |
| 05 | Benchmarks/onboarding metadata ownership | yes | Benchmark truth lives with builtins/domain metadata, not generic CLI code |
| 06 | Final domain folder migration | yes | Compatibility packages and old import paths are gone |

## PR Description Template

Every PR must include:

```markdown
### CLI Refactor Slice Ledger

Invariant landed:

Bridge code introduced:

Old path still intentionally alive:

Deletion gate:

Tests added or updated:

Modules owned by this PR:
```

## Parallelization Rules

Safe in parallel:

- Draft PR 01 tests while PR 00 hygiene lands.
- Draft PR 03 shared helpers after PR 02 parser module names are agreed.
- Draft PR 05 metadata catalogue while PR 04 works on runs/experiments.

Do not parallelize changes to:

- `ergon_cli/ergon_cli/main.py` across PR 00 and PR 02.
- `ergon_cli/ergon_cli/commands/workflow.py` across PR 00 and PR 01.
- `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py` across PR 01 and
  other builtins toolkit changes.

## Final Deleted Or Forbidden Paths

By PR 06:

- `ergon_cli/ergon_cli/bootstrap.py`
- production imports of `ergon_cli.commands.*`
- production imports of `ergon_cli.discovery`
- production imports of `ergon_cli.rendering`
- production imports of `ergon_builtins -> ergon_cli`
- the human CLI `ergon workflow manage ...` surface
- generic CLI hardcoded benchmark sandbox template paths
- direct persistence imports in converted CLI domains

## Final Architecture Guards

PR 06 must land tests asserting:

- `argparse.Namespace` does not pass below domain `commands.py`.
- Domain services do not import `argparse`.
- CLI domains do not import `ergon_core.core.persistence`.
- `ergon_builtins` production code does not import `ergon_cli`.
- Generic CLI code does not hardcode benchmark-specific metadata.
- Output printing lives at command/rendering boundaries, not service internals.
