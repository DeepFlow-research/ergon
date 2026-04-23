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
base="https://raw.githubusercontent.com/${repo}/screenshots/pr-${pr}/${env}"

# Enumerate images in the screenshots ref for this env.  We don't have
# a fetched copy of the ref locally (save the CPU); rely on the git
# refspec listing instead.
imgs_hash=$(git ls-remote "https://github.com/${repo}.git" "refs/heads/screenshots/pr-${pr}" | awk '{print $1}' || true)
if [ -z "${imgs_hash}" ]; then
  echo "no screenshots ref yet; skipping comment"
  exit 0
fi

body=$(cat <<EOF
## E2E smoke — \`${env}\`

Screenshots pushed to [\`screenshots/pr-${pr}\`](https://github.com/${repo}/tree/screenshots/pr-${pr}/${env}).

![${env} happy run](${base}/${env}-happy-run-full.png)
![${env} graph](${base}/${env}-graph.png)
![cohort](${base}/cohort-${env}.png)
EOF
)

# gh pr comment is idempotent-by-default: a new comment per invocation.
# Could dedup by matching body prefix, but per-matrix-leg comments are
# already distinct (env slug in first line) so duplicate noise is low.
gh pr comment "$pr" --body "$body" || {
  echo "warning: gh pr comment failed; screenshots still in ref"
  exit 0
}
