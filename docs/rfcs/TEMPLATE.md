---
status: active  # active | accepted | rejected
opened: YYYY-MM-DD
author: <human-or-agent>
architecture_refs: []  # e.g. [docs/architecture/02_runtime_lifecycle.md#task-state-machine]
supersedes: []
superseded_by: null
---

# RFC: <title>

## Problem

Why are we changing something? What invariant is this fixing, which gap is this
closing, or which capability is this adding? One or two paragraphs.

## Proposal

The change in one paragraph, then concrete specifics. Include code sketches,
type signatures, or SQL where it sharpens the proposal.

## Invariants affected

Which architecture-doc invariants does this introduce, change, or break? Cite
exact sections. If a new invariant is introduced, state it precisely.

## Migration

What breaks and must change in parallel? Data migrations? Alembic revision? 
Test rewrites? Downstream consumers?

## Alternatives considered

Options we rejected and why. Be honest — if a simpler option exists, say why
we aren't taking it.

## Open questions

Things we're deferring or need steer on. Mark with `@<person>` if a specific
person should decide.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Update the cited `architecture_refs` sections if invariants changed.
  - Link the implementation plan in `docs/superpowers/plans/`.
  - Close any related bug files in `docs/bugs/open/`.
