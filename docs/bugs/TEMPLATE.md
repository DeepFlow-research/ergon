---
status: open  # open | fixed
opened: YYYY-MM-DD
fixed_pr: null  # set to PR number when moved to fixed/
priority: P1  # P0 = production broken; P1 = silent data loss or ux break; P2 = correctness; P3 = cleanup
invariant_violated: null  # e.g. docs/architecture/03_providers.md#sandbox-event-sink
related_rfc: null  # if a fix is being designed, link RFC here
---

# Bug: <title>

## Symptom

What the user, operator, or system observes. Be concrete — log lines, wrong
values, missing events, etc. Not "X feels slow" — "X takes 45s when it should
take 3s, measured at commit <sha>."

## Repro

Exact steps. If there's a minimal test that reproduces it, point at that file
and line. If the bug is "runs forever / never happens in test", explain the
timing or state condition that triggers it.

## Root cause

If known. Link to the offending file and line (`path.py:123`). If not yet known,
state "unknown — investigation needed" and list what's been ruled out.

## Scope

Who's affected, how often, which workflows. "Every SWE-bench run" vs "only when
E2B template is stale" vs "observed once in staging."

## Proposed fix

One paragraph. If the fix is non-trivial, open an RFC and link it in
`related_rfc` above; this section then points to the RFC.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - If this bug violated an architecture invariant, confirm the invariant is
    restored (or the doc updated to reflect a revised invariant).
