# Workflow Agent CLI — Plan Folder

**Status:** draft for review.
**Date:** 2026-04-26.
**Scope:** build `ergon workflow ...`, an agent-local command surface for workflow topology/resource inspection, controlled resource materialization, and a ResearchRubrics ReAct proof of concept.

## Read Order

1. [`00-program.md`](00-program.md) — goal, architecture, non-goals, file plan.
2. [`01-resource-semantics.md`](01-resource-semantics.md) — immutable resources, copy/fork semantics, current-run invariant, lineage.
3. [`02-schema-and-services.md`](02-schema-and-services.md) — schema migration, DTOs, and the single workflow service.
4. [`03-cli-command-surface.md`](03-cli-command-surface.md) — `workflow inspect ...` and `workflow manage ...` commands.
5. [`04-agent-tool-and-worker.md`](04-agent-tool-and-worker.md) — pydantic-ai wrapper, permissions, ResearchRubrics POC worker.
6. [`05-tests-and-acceptance.md`](05-tests-and-acceptance.md) — unit, integration, e2e, and real-LLM acceptance gates.
7. [`06-phases.md`](06-phases.md) — phased implementation order and acceptance gates.

## Principle

Each document should be self-contained for its implementation area. If two docs disagree, [`00-program.md`](00-program.md) wins for scope and ownership, while [`01-resource-semantics.md`](01-resource-semantics.md) wins for resource semantics.

## Supersedes

This folder supersedes [`../2026-04-26-mas-navigation-cli.md`](../2026-04-26-mas-navigation-cli.md). Keep the old file only as a pointer while reviewers migrate.
