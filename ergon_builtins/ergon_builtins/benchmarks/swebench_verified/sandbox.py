"""SWEBenchSandbox — object-bound E2B sandbox for SWE-Bench Verified."""

from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox


class SWEBenchSandbox(E2BSandbox):
    """E2B-backed sandbox for SWE-Bench Verified instances."""

    template: str | None = "ergon-swebench-v1"
    repo_url: str | None = None
    base_commit: str | None = None
    requires_network: bool = True
