"""ResearchE2BSandbox — object-bound E2B sandbox for ResearchRubrics."""

from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox


class ResearchE2BSandbox(E2BSandbox):
    """E2B-backed sandbox for ResearchRubrics deep-research tasks."""

    template: str | None = "ergon-research-v1"
    requires_network: bool = True
    research_data_dir: str = "/workspace/research_data"
