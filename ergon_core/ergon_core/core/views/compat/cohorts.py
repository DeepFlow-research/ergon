"""Read-only DTOs for deprecated cohort dashboard compatibility."""

from ergon_core.core.application.compat.cohorts import (
    CohortDetailDto,
    CohortExperimentRowDto,
    CohortStatusCountsDto,
    CohortSummaryDto,
    UpdateCohortRequest,
)

__all__ = [
    "CohortDetailDto",
    "CohortExperimentRowDto",
    "CohortStatusCountsDto",
    "CohortSummaryDto",
    "UpdateCohortRequest",
]
