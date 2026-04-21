---
status: open
opened: 2026-04-18
fixed_pr: null
priority: P3
invariant_violated: null
related_rfc: null
---

# Bug: CI Docker layers are not cached between e2e workflow runs

## Symptom

CI jobs that use `docker-compose.ci.yml` rebuild Docker image layers on
every run. The result is a long tail of slow e2e CI wall-clock times: the
Postgres + Inngest + app stack gets rebuilt from scratch each time the
`e2e-benchmarks.yml` workflow fires, even when no Dockerfile or
dependency has changed. The same cost will be paid on every PR once the
integration tier (see
`docs/rfcs/active/2026-04-18-testing-posture-reset.md`) lands, because it
uses the same compose stack.

## Repro

Inspect the two files:

- `.github/workflows/e2e-benchmarks.yml` — no `actions/cache` step for
  Docker Buildx layers, no GHA Docker cache import, no pre-pull of
  pinned images.
- `docker-compose.ci.yml` — no `cache_from` or `cache_to` directives,
  no BuildKit configuration, no pinned image digests used as a cache
  base.

Triggering `workflow_dispatch` on `e2e-benchmarks.yml` twice in a row
shows a full rebuild on both runs.

## Root cause

No Docker layer caching is configured in CI. Neither the workflow nor
the compose file declares a cache source or target, so BuildKit has
nothing to read from. The images are also not pinned to specific
digests, so image-layer caching via `docker pull` does not apply
consistently either.

## Scope

- Every run of `e2e-benchmarks.yml`.
- Every future PR after the testing-posture-reset RFC lands and the
  integration tier starts using the same compose file on the hot path.
- Developers running the compose stack locally for the first time pay a
  similar cost, though less visible than CI.
- Not a correctness bug — no data loss, no wrong results. Pure CI
  latency and cost.

## Proposed fix

Three orthogonal improvements, do all three:

1. Add `actions/cache` for Docker Buildx layers in
   `e2e-benchmarks.yml`. Cache key by Dockerfile hash + compose-file
   hash + lockfiles.
2. Add `cache_from` + `cache_to` directives in `docker-compose.ci.yml`
   so BuildKit reads and writes a registry-backed cache (or a GHA
   cache, `type=gha`).
3. Pin third-party base images (Postgres, Inngest) to specific digests
   and `docker pull` them explicitly in a CI step before the compose
   build, so the base layers are always cache hits.

Alternative: switch to GitHub's native Docker build-push action which
bundles all three behaviors. Lower blast radius per step, fewer knobs to
tune.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Measure the improvement: before/after wall-clock on
    `e2e-benchmarks.yml` for a no-op change. Record in the PR
    description.
  - If integration-tier Docker caching lands in the same PR, note that
    here.
