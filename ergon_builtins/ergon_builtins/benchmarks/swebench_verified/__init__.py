"""SWE-Bench Verified benchmark package."""

# SweBenchVerifiedBenchmark is intentionally NOT re-exported here.
# benchmark.py imports SWEBenchSandbox from
# ergon_builtins.benchmarks.swebench_verified.sandbox, and sandbox.py
# imports SWEBenchSandboxManager from this package.  Eagerly re-exporting
# SweBenchVerifiedBenchmark would complete a cycle:
#   benchmarks/swebench_verified/sandbox.py → benchmarks.swebench_verified (here)
#   → benchmark.py → benchmarks/swebench_verified/sandbox.py
# All call sites that need SweBenchVerifiedBenchmark import it directly:
#   from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
#
# TODO(PR 11): once `sandbox.py` no longer imports `SWEBenchSandboxManager`
# (PR 11 deletes the manager and rewrites `provision()` to call E2B
# directly), the cycle is broken and `SweBenchVerifiedBenchmark` can be
# added back to the eager exports.
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)

__all__ = [
    "SWEBenchInstance",
    "SWEBenchRubric",
    "SWEBenchTaskPayload",
]
