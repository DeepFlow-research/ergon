"""MiniF2F benchmark for formal math proof verification."""

# MiniF2FBenchmark is intentionally NOT re-exported here.  benchmark.py
# imports LeanSandbox from ergon_builtins.sandboxes, and lean.py imports
# MiniF2FSandboxManager from this package.  Eagerly re-exporting
# MiniF2FBenchmark would complete a cycle:
#   sandboxes/__init__.py → lean.py → benchmarks.minif2f (here)
#   → benchmark.py → sandboxes/__init__.py
# All call sites that need MiniF2FBenchmark import it directly:
#   from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
#
# TODO(PR 11): once `lean.py` no longer imports `MiniF2FSandboxManager`
# (PR 11 deletes the manager and rewrites `provision()` to call E2B
# directly), the cycle is broken and `MiniF2FBenchmark` can be added
# back to the eager exports.
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.rules.proof_verification import (
    ProofVerificationCriterion,
)
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem, MiniF2FTaskPayload

__all__ = [
    "MiniF2FProblem",
    "MiniF2FRubric",
    "MiniF2FTaskPayload",
    "ProofVerificationCriterion",
]
