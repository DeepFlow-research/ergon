from typing import ClassVar

from ergon_builtins.sandbox_runtime import E2BSandbox

from ergon_builtins.benchmarks.minif2f.sandbox.utils import (
    resolve_template,
)

class MiniF2FSandbox(E2BSandbox):
    """Public MiniF2F sandbox definition."""

    template: ClassVar[str | None] = resolve_template()
