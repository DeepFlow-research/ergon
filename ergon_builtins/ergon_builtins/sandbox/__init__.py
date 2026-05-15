"""Cross-cutting sandbox infrastructure shared across benchmarks.

Files in this package implement adapters / utilities that more than
one benchmark's `Sandbox` subclass relies on.  Per-benchmark code
(`LeanSandbox`, `SWEBenchSandbox`, etc.) lives in
`ergon_builtins/benchmarks/<slug>/sandbox.py`, NOT here.

Naming: singular ``sandbox/`` (this package, cross-cutting infra)
vs. per-benchmark ``benchmarks/<slug>/sandbox.py`` (single concrete
Sandbox subclass).  The deleted ``sandboxes/`` (plural) directory
conflated the two and is gone.

PR 10a populates this with ``_manager_backed.py`` (the shared
BaseSandboxManager → SandboxRuntime adapter).
"""
