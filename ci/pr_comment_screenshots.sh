#!/usr/bin/env bash
# Post a per-leg PR comment linking the screenshots pushed to
# ``screenshots/pr-<N>``.
#
# Usage: pr_comment_screenshots.sh <pr_number> <env>
#
# Best-effort: missing images fall through gracefully (caller may have
# hit Playwright early-exit paths).  Does not fail the CI job on
# comment errors — screenshots in the git ref are the primary artifact.

set -euo pipefail

pr="${1:?missing PR number}"
env="${2:?missing env slug}"
repo="${GITHUB_REPOSITORY:-DeepFlow-research/ergon}"

# Enumerate images in the screenshots ref for this env so comments
# match the files Playwright actually emitted for this run.
imgs_hash=$(git ls-remote origin "refs/heads/screenshots/pr-${pr}" | awk '{print $1}' || true)
if [ -z "${imgs_hash}" ]; then
  echo "no screenshots ref yet; skipping comment"
  exit 0
fi

git fetch --depth=1 origin "refs/heads/screenshots/pr-${pr}:refs/remotes/origin/screenshots/pr-${pr}" >/dev/null
images=$(git ls-tree -r --name-only "origin/screenshots/pr-${pr}" -- "${env}" | grep '\.png$' | sort || true)

if [ -z "${images}" ]; then
  body=$(cat <<EOF
## E2E smoke — \`${env}\`

No PNG screenshots were uploaded for this leg. See [\`screenshots/pr-${pr}\`](https://github.com/${repo}/tree/screenshots/pr-${pr}/${env}) for the uploaded placeholder.
EOF
)
else
  image_markdown=""
  while IFS= read -r image; do
    image_markdown+=$(printf '![%s](https://raw.githubusercontent.com/%s/screenshots/pr-%s/%s)' "$image" "$repo" "$pr" "$image")
    image_markdown+=$'\n'
  done <<< "${images}"
  body=$(cat <<EOF
## E2E smoke — \`${env}\`

Screenshots pushed to [\`screenshots/pr-${pr}\`](https://github.com/${repo}/tree/screenshots/pr-${pr}/${env}).

${image_markdown}
EOF
)
fi

# gh pr comment is idempotent-by-default: a new comment per invocation.
# Could dedup by matching body prefix, but per-matrix-leg comments are
# already distinct (env slug in first line) so duplicate noise is low.
gh pr comment "$pr" --body "$body" || {
  echo "warning: gh pr comment failed; screenshots still in ref"
  exit 0
}
