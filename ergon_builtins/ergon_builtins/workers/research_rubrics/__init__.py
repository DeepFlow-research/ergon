"""ResearchRubrics worker subclasses (manager + researcher)."""

from ergon_builtins.workers.research_rubrics.manager_worker import (
    ResearchRubricsManagerWorker,
)
from ergon_builtins.workers.research_rubrics.researcher_worker import (
    ResearchRubricsResearcherWorker,
)

__all__ = [
    "ResearchRubricsManagerWorker",
    "ResearchRubricsResearcherWorker",
]
