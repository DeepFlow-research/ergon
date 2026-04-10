"""CRUD repository for saved-spec tables."""

from typing import TypeVar
from uuid import UUID

from h_arcane.core.persistence.saved_specs.models import (
    SavedBenchmarkSpec,
    SavedEvaluatorSpec,
    SavedExperimentTemplate,
    SavedWorkerSpec,
)
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.utils import utcnow
from sqlmodel import SQLModel, select

T = TypeVar("T", bound=SQLModel)


class SavedSpecsRepository:
    """Unified CRUD for all saved-spec tables."""

    # ------------------------------------------------------------------
    # Benchmark specs
    # ------------------------------------------------------------------

    def get_benchmark_spec(self, spec_id: UUID) -> SavedBenchmarkSpec | None:
        with get_session() as session:
            return session.get(SavedBenchmarkSpec, spec_id)

    def list_benchmark_specs(self) -> list[SavedBenchmarkSpec]:
        with get_session() as session:
            return list(session.exec(select(SavedBenchmarkSpec)).all())

    def create_benchmark_spec(self, **kwargs: object) -> SavedBenchmarkSpec:
        return self._create(SavedBenchmarkSpec, **kwargs)

    def update_benchmark_spec(self, spec_id: UUID, **kwargs: object) -> SavedBenchmarkSpec | None:
        return self._update(SavedBenchmarkSpec, spec_id, **kwargs)

    # ------------------------------------------------------------------
    # Worker specs
    # ------------------------------------------------------------------

    def get_worker_spec(self, spec_id: UUID) -> SavedWorkerSpec | None:
        with get_session() as session:
            return session.get(SavedWorkerSpec, spec_id)

    def list_worker_specs(self) -> list[SavedWorkerSpec]:
        with get_session() as session:
            return list(session.exec(select(SavedWorkerSpec)).all())

    def create_worker_spec(self, **kwargs: object) -> SavedWorkerSpec:
        return self._create(SavedWorkerSpec, **kwargs)

    def update_worker_spec(self, spec_id: UUID, **kwargs: object) -> SavedWorkerSpec | None:
        return self._update(SavedWorkerSpec, spec_id, **kwargs)

    # ------------------------------------------------------------------
    # Evaluator specs
    # ------------------------------------------------------------------

    def get_evaluator_spec(self, spec_id: UUID) -> SavedEvaluatorSpec | None:
        with get_session() as session:
            return session.get(SavedEvaluatorSpec, spec_id)

    def list_evaluator_specs(self) -> list[SavedEvaluatorSpec]:
        with get_session() as session:
            return list(session.exec(select(SavedEvaluatorSpec)).all())

    def create_evaluator_spec(self, **kwargs: object) -> SavedEvaluatorSpec:
        return self._create(SavedEvaluatorSpec, **kwargs)

    def update_evaluator_spec(self, spec_id: UUID, **kwargs: object) -> SavedEvaluatorSpec | None:
        return self._update(SavedEvaluatorSpec, spec_id, **kwargs)

    # ------------------------------------------------------------------
    # Experiment templates
    # ------------------------------------------------------------------

    def get_experiment_template(self, template_id: UUID) -> SavedExperimentTemplate | None:
        with get_session() as session:
            return session.get(SavedExperimentTemplate, template_id)

    def list_experiment_templates(self) -> list[SavedExperimentTemplate]:
        with get_session() as session:
            return list(session.exec(select(SavedExperimentTemplate)).all())

    def create_experiment_template(self, **kwargs: object) -> SavedExperimentTemplate:
        return self._create(SavedExperimentTemplate, **kwargs)

    def update_experiment_template(
        self,
        template_id: UUID,
        **kwargs: object,
    ) -> SavedExperimentTemplate | None:
        return self._update(SavedExperimentTemplate, template_id, **kwargs)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create(model_class: type[T], **kwargs: object) -> T:
        with get_session() as session:
            row = model_class(**kwargs)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    @staticmethod
    def _update(model_class: type[T], row_id: UUID, **kwargs: object) -> T | None:
        with get_session() as session:
            row = session.get(model_class, row_id)
            if row is None:
                return None
            for key, value in kwargs.items():
                setattr(row, key, value)
            if hasattr(row, "updated_at"):  # slopcop: ignore[no-hasattr-getattr]
                row.updated_at = utcnow()
            session.add(row)
            session.commit()
            session.refresh(row)
            return row


saved_specs_repository = SavedSpecsRepository()
