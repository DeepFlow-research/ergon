"""Compatibility imports for the ResearchRubrics sad-path fixture."""

from ergon_core.test_support.smoke_fixtures.smoke_base.sadpath import AlwaysFailSubworker
from ergon_core.test_support.smoke_fixtures.workers.researchrubrics_smoke import (
    ResearchRubricsFailingLeafWorker,
    ResearchRubricsSadPathSmokeWorker,
)


__all__ = [
    "AlwaysFailSubworker",
    "ResearchRubricsFailingLeafWorker",
    "ResearchRubricsSadPathSmokeWorker",
]
