/**
 * Mirror of ``tests/e2e/_fixtures/smoke_base/constants.py``.
 *
 * Duplicated intentionally — cross-language import would add build
 * complexity for no real benefit, and both files are short enough that
 * drift is loud in code review.
 */

export const EXPECTED_SUBTASK_SLUGS = [
  "d_root",
  "d_left",
  "d_right",
  "d_join",
  "l_1",
  "l_2",
  "l_3",
  "s_a",
  "s_b",
] as const;

export const EXPECTED_NESTED_SUBTASK_SLUGS = ["l_2_a", "l_2_b"] as const;
