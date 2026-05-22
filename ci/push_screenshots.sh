#!/usr/bin/env bash
# Push per-PR Playwright screenshots to a dedicated git ref.
#
# Usage: push_screenshots.sh <pr_number> <env> <screenshot_dir>
#
# Creates/updates the orphan branch ``screenshots/pr-<N>`` and pushes
# PNGs under ``<env>/``.  Idempotent — re-running adds a new commit but
# never overwrites prior screenshots from other matrix legs.
#
# Called from tests/e2e/conftest.py's session-scoped _screenshot_uploader
# finalizer; also called directly from the CI workflow "Push
# screenshots" step so uploads happen on pytest hard-failures too.

set -euo pipefail

pr="${1:?missing PR number}"
env="${2:?missing env slug}"
dir="${3:?missing screenshot dir}"
branch="screenshots/pr-${pr}"

# Configure identity (GitHub Actions has no default).
git config user.name  "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

# Move to repo root so relative paths work regardless of where the
# script is invoked.
cd "$(git rev-parse --show-toplevel)"
repo_root="$(pwd)"
case "$dir" in
  /*) source_dir="$dir" ;;
  *) source_dir="${repo_root}/${dir}" ;;
esac

worktree_dir="$(mktemp -d)"
cleanup_worktree() {
  git -C "$repo_root" worktree remove --force "$worktree_dir" >/dev/null 2>&1 || rm -rf "$worktree_dir"
}
trap cleanup_worktree EXIT

# Fetch or init the screenshots branch in an isolated worktree so the
# live CI checkout stays on the PR tree for diagnostics and teardown.
if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
  git fetch origin "$branch"
  git worktree add --detach "$worktree_dir" FETCH_HEAD
else
  git worktree add --detach "$worktree_dir" HEAD
  cd "$worktree_dir"
  git checkout --orphan "$branch"
  git rm -rf . >/dev/null 2>&1 || true
  printf "Screenshots for PR #%s\n" "$pr" > README.md
  git add README.md
  git commit -m "ci: init screenshots/pr-${pr}"
fi

cd "$worktree_dir"

stage_env_screenshots() {
  rm -rf "${env}"
  mkdir -p "${env}"
  if compgen -G "${source_dir}/${env}/*.png" > /dev/null; then
    cp -r "${source_dir}/${env}"/*.png "${env}/"
  else
    # No screenshots captured (e.g., Playwright failed before first
    # page.screenshot).  Emit a placeholder so the PR comment can still
    # link a path and the absence becomes visible.
    printf "No screenshots captured for %s on this run.\n" "$env" \
      > "${env}/EMPTY.txt"
  fi

  echo "screenshot upload source: ${source_dir}/${env}"
  find "${env}" -maxdepth 1 -type f | sort

  git add "${env}/"
  if ! git diff --cached --quiet; then
    git commit -m "ci: screenshots ${env} $(date -u +%Y%m%dT%H%M%SZ)"
  fi
}

stage_env_screenshots
for attempt in 1 2 3; do
  if git push origin "HEAD:${branch}"; then
    exit 0
  fi
  if [ "$attempt" -eq 3 ]; then
    echo "failed to push screenshots after ${attempt} attempts" >&2
    exit 1
  fi

  # Matrix legs can race when they all create/update the same
  # screenshots branch. Refresh from the remote branch, restage this
  # leg's screenshots, and retry so an upload race does not fail an
  # otherwise successful smoke.
  sleep "$attempt"
  git fetch origin "$branch"
  git reset --hard FETCH_HEAD
  stage_env_screenshots
done
