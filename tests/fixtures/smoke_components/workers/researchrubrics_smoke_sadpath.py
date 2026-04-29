"""Compatibility imports for the ResearchRubrics sad-path fixture."""

from tests.fixtures.smoke_components.smoke_base.sadpath import AlwaysFailSubworker
from tests.fixtures.smoke_components.workers.researchrubrics_smoke import (
    ResearchRubricsFailingLeafWorker,
    ResearchRubricsSadPathSmokeWorker,
)
