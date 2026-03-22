"""FastAPI router for experiment cohort endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from h_arcane.core._internal.cohorts import (
    CohortDetailDto,
    CohortSummaryDto,
    UpdateCohortRequest,
    experiment_cohort_service,
)

router = APIRouter(prefix="/cohorts", tags=["cohorts"])


@router.get("", response_model=list[CohortSummaryDto])
def list_cohorts(include_archived: bool = Query(default=False)) -> list[CohortSummaryDto]:
    """List all experiment cohorts."""
    return experiment_cohort_service.list_summaries(include_archived=include_archived)


@router.get("/{cohort_id}", response_model=CohortDetailDto)
def get_cohort(cohort_id: UUID) -> CohortDetailDto:
    """Get one cohort detail payload."""
    detail = experiment_cohort_service.get_detail(cohort_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Cohort {cohort_id} not found")
    return detail


@router.patch("/{cohort_id}", response_model=CohortSummaryDto)
def update_cohort(cohort_id: UUID, request: UpdateCohortRequest) -> CohortSummaryDto:
    """Update one cohort's operator-managed fields."""
    summary = experiment_cohort_service.update_cohort(cohort_id, request)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Cohort {cohort_id} not found")
    return summary
