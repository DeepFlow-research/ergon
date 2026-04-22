"""Per-benchmark adapters plugged into the unified :class:`ReActWorker`.

Composition-over-inheritance: rather than subclassing ReActWorker per
benchmark, each benchmark ships an adapter that owns its toolkit, setup
hooks, post-run artifact extraction, and output routing. The ReActWorker
holds a single adapter reference and delegates those concerns to it.
"""

from ergon_builtins.workers.baselines.adapters.base import BenchmarkAdapter
from ergon_builtins.workers.baselines.adapters.minif2f import MiniF2FAdapter
from ergon_builtins.workers.baselines.adapters.swebench import SWEBenchAdapter

__all__ = [
    "BenchmarkAdapter",
    "MiniF2FAdapter",
    "SWEBenchAdapter",
]
