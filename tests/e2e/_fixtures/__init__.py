"""Test-only worker / criterion registration hook.

Importing this package registers the per-env canonical-smoke workers,
leaves, and criteria into the process-level ``WORKERS`` / ``EVALUATORS``
dicts from ``ergon_builtins.registry``.  Production CLI paths do not
import ``tests/``, so registrations here are confined to test runtimes.

Phase C (this commit) adds the researchrubrics happy + sad-path rows.
Phase D adds minif2f and swebench-verified.  Idempotent: calling twice
is a no-op (``dict`` assignment is the mechanism).

See docs/superpowers/plans/test-refactor/01-fixtures.md §2.7.
"""

from ergon_builtins.registry import EVALUATORS, WORKERS

from tests.e2e._fixtures.criteria.minif2f_smoke import MiniF2FSmokeCriterion
from tests.e2e._fixtures.criteria.researchrubrics_smoke import (
    ResearchRubricsSmokeCriterion,
)
from tests.e2e._fixtures.criteria.swebench_smoke import SweBenchSmokeCriterion
from tests.e2e._fixtures.workers.minif2f_smoke import (
    MiniF2FSmokeLeafWorker,
    MiniF2FSmokeWorker,
)
from tests.e2e._fixtures.workers.researchrubrics_smoke import (
    ResearchRubricsSmokeLeafWorker,
    ResearchRubricsSmokeWorker,
)
from tests.e2e._fixtures.workers.researchrubrics_smoke_sadpath import (
    ResearchRubricsFailingLeafWorker,
    ResearchRubricsSadPathSmokeWorker,
)
from tests.e2e._fixtures.workers.swebench_smoke import (
    SweBenchSmokeLeafWorker,
    SweBenchSmokeWorker,
)


def register_smoke_fixtures() -> None:
    """Register the per-env smoke worker + criterion slugs.

    Called on import (below) so the fixtures are available by the time
    the e2e pytest session starts executing test modules.  Idempotent:
    calling multiple times reassigns the same dict entries without
    side-effects.
    """
    # ResearchRubrics happy-path
    WORKERS[ResearchRubricsSmokeWorker.type_slug] = ResearchRubricsSmokeWorker
    WORKERS[ResearchRubricsSmokeLeafWorker.type_slug] = ResearchRubricsSmokeLeafWorker
    EVALUATORS[ResearchRubricsSmokeCriterion.type_slug] = ResearchRubricsSmokeCriterion

    # ResearchRubrics sad-path (cohort slot 3)
    WORKERS[ResearchRubricsSadPathSmokeWorker.type_slug] = ResearchRubricsSadPathSmokeWorker
    WORKERS[ResearchRubricsFailingLeafWorker.type_slug] = ResearchRubricsFailingLeafWorker

    # MiniF2F happy-path
    WORKERS[MiniF2FSmokeWorker.type_slug] = MiniF2FSmokeWorker
    WORKERS[MiniF2FSmokeLeafWorker.type_slug] = MiniF2FSmokeLeafWorker
    EVALUATORS[MiniF2FSmokeCriterion.type_slug] = MiniF2FSmokeCriterion

    # SWE-Bench Verified happy-path
    WORKERS[SweBenchSmokeWorker.type_slug] = SweBenchSmokeWorker
    WORKERS[SweBenchSmokeLeafWorker.type_slug] = SweBenchSmokeLeafWorker
    EVALUATORS[SweBenchSmokeCriterion.type_slug] = SweBenchSmokeCriterion


register_smoke_fixtures()
