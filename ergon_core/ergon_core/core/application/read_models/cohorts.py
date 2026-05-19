"""Deprecated import shim for cohort compatibility DTOs.

Production code should import cohort compatibility behavior from
``ergon_core.core.application.compat.cohorts`` or read-only cohort DTOs from
``ergon_core.core.views.compat.cohorts``. This shim stays only to avoid turning
PR 08 into the cohort deletion PR.
"""

from ergon_core.core.application.compat.cohorts import (
    CohortDetailDto,
    CohortExperimentRowDto,
    CohortStatusCountsDto,
    CohortSummaryDto,
    DeprecatedCohortCompatibilityService,
    ResolveCohortRequest,
    RubricStatusSummary,
    UpdateCohortRequest,
    deprecated_cohort_compatibility_service,
)

ExperimentCohortService = DeprecatedCohortCompatibilityService
experiment_cohort_service = deprecated_cohort_compatibility_service

__all__ = [
    "CohortDetailDto",
    "CohortExperimentRowDto",
    "CohortStatusCountsDto",
    "CohortSummaryDto",
    "DeprecatedCohortCompatibilityService",
    "ExperimentCohortService",
    "ResolveCohortRequest",
    "RubricStatusSummary",
    "UpdateCohortRequest",
    "deprecated_cohort_compatibility_service",
    "experiment_cohort_service",
]
