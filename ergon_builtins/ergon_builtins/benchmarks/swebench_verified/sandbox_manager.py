"""SWE-Bench Verified public sandbox definition."""

from typing import ClassVar

from ergon_builtins.benchmarks.swebench_verified.sandbox.utils import resolve_template
from ergon_builtins.sandbox_runtime import E2BSandbox


class SWEBenchSandbox(E2BSandbox):
    """Public SWE-Bench sandbox definition."""

    template: ClassVar[str | None] = resolve_template()
