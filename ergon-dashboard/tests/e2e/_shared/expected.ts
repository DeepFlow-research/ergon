/**
 * Mirror of ``tests/e2e/_fixtures/smoke_base/constants.py``.
 *
 * Duplicated intentionally — cross-language import would add build
 * complexity for no real benefit, and both files are short enough that
 * drift is loud in code review.
 */

export const EXPECTED_SUBTASK_SLUGS = [
  "source-review",
  "handoff-verify",
  "primary-artifact",
  "artifact-summary",
  "metadata-review",
  "environment-probe",
  "metadata-validate",
  "evidence-artifact",
  "completion-marker",
] as const;

export const EXPECTED_NESTED_SUBTASK_SLUGS = [
  "nested-input-review",
  "nested-verification",
] as const;
