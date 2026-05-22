"""LeanSandbox — object-bound Lean 4 sandbox for MiniF2F."""

from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox


class LeanSandbox(E2BSandbox):
    """Lean 4 E2B sandbox for MiniF2F."""

    lean_version: str = "4.7.0"
    template: str | None = "ergon-minif2f-v1"
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"
