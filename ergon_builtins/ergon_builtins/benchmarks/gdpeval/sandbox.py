"""GDPEvalSandbox — object-bound E2B sandbox for GDPEval."""

from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox


class GDPEvalSandbox(E2BSandbox):
    """E2B-backed sandbox for GDPEval document-processing tasks."""

    template: str | None = "ergon-gdpeval-v1"
    requires_network: bool = False
    workspace_dir: str = "/workspace/gdpeval"
