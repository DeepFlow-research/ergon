# Release Process

Ergon uses a lightweight release-train model.

## Branches

- `main` is the stable release branch. Every merge to `main` is expected to be releasable.
- `dev` is the integration branch for normal feature and fix work.
- `feature/*`, `fix/*`, and `codex/*` branches should target `dev` by default.
- `release/vX.Y.Z` branches are optional short-lived stabilization branches created from `dev`.
- `hotfix/vX.Y.Z` branches are created from `main` for urgent production fixes and must be backmerged to `dev`.

## Normal Flow

1. Open feature and fix PRs against `dev`.
2. Keep `dev` green.
3. When `dev` is ready to release, update `project.version` in `pyproject.toml`.
4. Open a release PR from `dev` to `main`.
5. Merge the release PR after required checks pass.
6. The release tagger creates `vX.Y.Z` from the version in `pyproject.toml` and publishes a GitHub Release.
7. If release-only changes landed on `main`, merge `main` back into `dev`.

## Hotfix Flow

1. Branch from `main` as `hotfix/vX.Y.Z`.
2. Apply the smallest safe fix and bump `project.version`.
3. Open the hotfix PR against `main`.
4. Merge after checks pass; the release tagger publishes the patch release.
5. Backmerge or cherry-pick the hotfix into `dev`.

## Release Tagger Rules

- The tag name is `v` plus `project.version` from the root `pyproject.toml`.
- `project.version` must look like SemVer, for example `0.1.0` or `0.1.1`.
- If the tag already exists at the same commit, the workflow exits cleanly.
- If the tag already exists at a different commit, the workflow fails.
