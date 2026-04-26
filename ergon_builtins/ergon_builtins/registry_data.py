"""Components that require the [data] capability (pandas, datasets, HF hub).

Eager, fully-typed imports.
"""

from collections.abc import Callable

from ergon_core.api import Benchmark, Evaluator, Worker
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
    ResearchRubricsSandboxManager,
)

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.vanilla import (
    ResearchRubricsVanillaBenchmark,
)
from ergon_builtins.workers.research_rubrics.researcher_worker import (
    ResearchRubricsResearcherWorker,
)
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import (
    ResearchRubricsWorkflowCliReActWorker,
)

BENCHMARKS: dict[str, type[Benchmark]] = {
    "gdpeval": GDPEvalBenchmark,
    "researchrubrics": ResearchRubricsBenchmark,
    "researchrubrics-ablated": ResearchRubricsBenchmark,
    "researchrubrics-vanilla": ResearchRubricsVanillaBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "research-rubric": ResearchRubricsRubric,
    "researchrubrics-rubric": ResearchRubricsRubric,
}

# reason: RFC 2026-04-22 §1 — base ``Worker.__init__`` now requires
# ``task_id`` / ``sandbox_id`` kwargs, and every registered worker subclass
# forwards them through to ``super().__init__``. The registry therefore
# stores the bare class (``WorkerFactory = Callable[..., Worker]``) and
# ``_plain`` has been deleted.
WORKERS: dict[str, Callable[..., Worker]] = {
    "researchrubrics-researcher": ResearchRubricsResearcherWorker,
    "researchrubrics-workflow-cli-react": ResearchRubricsWorkflowCliReActWorker,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "researchrubrics": ResearchRubricsSandboxManager,
    "researchrubrics-ablated": ResearchRubricsSandboxManager,
    "researchrubrics-vanilla": ResearchRubricsSandboxManager,
}
