-- Hand-written Lean 4 proof of miniF2F v2c problem `mathd_algebra_176`.
-- Pure ring identity: (x + 1)^2 * x = x^3 + 2x^2 + x.
-- Used by tests/minif2f/test_verification_integration.py to exercise the
-- sandbox → ProofVerificationCriterion pipeline with no model in the loop.
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Rat Finset

theorem mathd_algebra_176 (x : ℝ) : (x + 1) ^ 2 * x = x ^ 3 + 2 * x ^ 2 + x := by
  ring
