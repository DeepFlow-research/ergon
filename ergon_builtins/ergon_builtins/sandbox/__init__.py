"""Cross-cutting sandbox infrastructure shared across benchmarks.

Files in this package implement adapters / utilities that more than
one benchmark's `Sandbox` subclass relies on.  Per-benchmark code
(`LeanSandbox`, `SWEBenchSandbox`, etc.) lives in
`ergon_builtins/benchmarks/<slug>/sandbox.py`, NOT here. E2B-backed
benchmarks share ``E2BSandbox`` and ``E2BSandboxRuntime`` from this package.

Naming: singular ``sandbox/`` (this package, cross-cutting infra)
vs. per-benchmark ``benchmarks/<slug>/sandbox.py`` (single concrete
Sandbox subclass).  The deleted ``sandboxes/`` (plural) directory
conflated the two and is gone.
"""

from ergon_builtins.sandbox.e2b_runtime import E2BSandboxRuntime
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox

__all__ = ["E2BSandbox", "E2BSandboxRuntime"]
