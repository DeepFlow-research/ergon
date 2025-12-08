"""Database query methods organized by entity."""

from uuid import UUID
from typing import TypeVar, Generic, Type
from sqlmodel import SQLModel, select

from h_arcane.db.connection import get_session
from h_arcane.db.models import (
    Experiment,
    Run,
    RunStatus,
    Message,
    Action,
    Resource,
    Evaluation,
    CriterionResult,
    TaskEvaluationResult,
)


T = TypeVar("T", bound=SQLModel)


class BaseQueries(Generic[T]):
    """Base query class with common CRUD operations."""

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, id: UUID) -> T | None:
        """Get entity by ID."""
        with next(get_session()) as session:
            return session.get(self.model, id)

    def create(self, **kwargs) -> T:
        """Create a new entity."""
        entity = self.model(**kwargs)
        with next(get_session()) as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity

    def update(self, id: UUID, **kwargs) -> T:
        """Update entity fields."""
        with next(get_session()) as session:
            entity = session.get(self.model, id)
            if entity is None:
                raise ValueError(f"{self.model.__name__} {id} not found")
            for key, value in kwargs.items():
                setattr(entity, key, value)
            session.commit()
            session.refresh(entity)
            return entity


class RunsQueries(BaseQueries[Run]):
    """Query methods for Run model."""

    def __init__(self):
        super().__init__(Run)

    @staticmethod
    def get_by_status(status: RunStatus) -> list[Run]:
        """Get all runs with given status."""
        with next(get_session()) as session:
            statement = select(Run).where(Run.status == status)
            return list(session.exec(statement).all())  # type: ignore[attr-defined]

    @staticmethod
    def get_stats() -> dict:
        """Get run statistics."""
        with next(get_session()) as session:
            total = session.exec(select(Run)).all()  # type: ignore[attr-defined]
            return {
                "total": len(total),
                "pending": sum(1 for r in total if r.status == RunStatus.PENDING),
                "running": sum(
                    1 for r in total if r.status in [RunStatus.EXECUTING, RunStatus.EVALUATING]
                ),
                "completed": sum(1 for r in total if r.status == RunStatus.COMPLETED),
                "failed": sum(1 for r in total if r.status == RunStatus.FAILED),
            }

    def reset_for_retry(self, run_id: UUID) -> Run:
        """Reset run for retry."""
        return self.update(
            run_id,
            status=RunStatus.PENDING,
            error_message=None,
            started_at=None,
            completed_at=None,
        )


class ExperimentsQueries(BaseQueries[Experiment]):
    """Query methods for Experiment model."""

    def __init__(self):
        super().__init__(Experiment)

    @staticmethod
    def get_by_task_id(task_id: str) -> Experiment | None:
        """Get experiment by GDPEval task ID."""
        with next(get_session()) as session:
            statement = select(Experiment).where(Experiment.gdpeval_task_id == task_id)
            return session.exec(statement).first()  # type: ignore[attr-defined]


class ResourcesQueries(BaseQueries[Resource]):
    """Query methods for Resource model."""

    def __init__(self):
        super().__init__(Resource)

    @staticmethod
    def get_by_experiment(experiment_id: UUID) -> list[Resource]:
        """Get all input resources for an experiment."""
        with next(get_session()) as session:
            statement = select(Resource).where(Resource.experiment_id == experiment_id)
            return list(session.exec(statement).all())  # type: ignore[attr-defined]

    @staticmethod
    def get_by_run(run_id: UUID) -> list[Resource]:
        """Get all output resources for a run."""
        with next(get_session()) as session:
            statement = select(Resource).where(Resource.run_id == run_id)
            return list(session.exec(statement).all())  # type: ignore[attr-defined]

    @staticmethod
    def get_all(run_id: UUID | None = None, experiment_id: UUID | None = None) -> list[Resource]:
        """Get all resources, optionally filtered by run_id or experiment_id."""
        with next(get_session()) as session:
            statement = select(Resource)
            if run_id:
                statement = statement.where(Resource.run_id == run_id)
            if experiment_id:
                statement = statement.where(Resource.experiment_id == experiment_id)
            return list(session.exec(statement).all())  # type: ignore[attr-defined]


class MessagesQueries(BaseQueries[Message]):
    """Query methods for Message model."""

    def __init__(self):
        super().__init__(Message)

    @staticmethod
    def get_all(run_id: UUID, order_by: str = "sequence_num") -> list[Message]:
        """Get all messages for a run, ordered by sequence_num."""
        with next(get_session()) as session:
            statement = select(Message).where(Message.run_id == run_id)
            if order_by == "sequence_num":
                statement = statement.order_by(Message.sequence_num)  # type: ignore[arg-type]
            return list(session.exec(statement).all())  # type: ignore[attr-defined]


class ActionsQueries(BaseQueries[Action]):
    """Query methods for Action model."""

    def __init__(self):
        super().__init__(Action)

    @staticmethod
    def get_all(run_id: UUID, order_by: str = "action_num") -> list[Action]:
        """Get all actions for a run, ordered by action_num."""
        with next(get_session()) as session:
            statement = select(Action).where(Action.run_id == run_id)
            if order_by == "action_num":
                statement = statement.order_by(Action.action_num)  # type: ignore[arg-type]
            return list(session.exec(statement).all())  # type: ignore[attr-defined]


class EvaluationsQueries(BaseQueries[Evaluation]):
    """Query methods for Evaluation model."""

    def __init__(self):
        super().__init__(Evaluation)

    @staticmethod
    def get_by_run(run_id: UUID) -> Evaluation | None:
        """Get evaluation for a run."""
        with next(get_session()) as session:
            statement = select(Evaluation).where(Evaluation.run_id == run_id)
            return session.exec(statement).first()  # type: ignore[attr-defined]

    def create_from_eval(
        self,
        run_id: UUID,
        eval_result: Evaluation,
    ) -> Evaluation:
        """Create or update Evaluation from evaluation model (idempotent)."""
        # Check if evaluation already exists for this run_id
        existing = self.get_by_run(run_id)

        if existing:
            # Update existing evaluation
            return self.update(
                id=existing.id,
                total_score=eval_result.total_score,
                max_score=eval_result.max_score,
                normalized_score=eval_result.normalized_score,
                stages_evaluated=eval_result.stages_evaluated,
                stages_passed=eval_result.stages_passed,
                failed_gate=eval_result.failed_gate,
            )
        else:
            # Create new evaluation
            return self.create(
                run_id=eval_result.run_id,
                total_score=eval_result.total_score,
                max_score=eval_result.max_score,
                normalized_score=eval_result.normalized_score,
                stages_evaluated=eval_result.stages_evaluated,
                stages_passed=eval_result.stages_passed,
                failed_gate=eval_result.failed_gate,
            )


class CriterionResultsQueries(BaseQueries[CriterionResult]):
    """Query methods for CriterionResult model."""

    def __init__(self):
        super().__init__(CriterionResult)

    @staticmethod
    def get_all(
        run_id: UUID,
        order_by: list[str] | None = None,
    ) -> list[CriterionResult]:
        """Get all criterion results for a run."""
        with next(get_session()) as session:
            statement = select(CriterionResult).where(CriterionResult.run_id == run_id)
            if order_by:
                for field in order_by:
                    field_attr = getattr(CriterionResult, field, None)
                    if field_attr is not None:
                        statement = statement.order_by(field_attr)  # type: ignore[arg-type]
            return list(session.exec(statement).all())  # type: ignore[attr-defined]

    def create_from_eval(
        self,
        run_id: UUID,
        eval_result: CriterionResult,
    ) -> CriterionResult:
        """Create CriterionResult from evaluation model."""
        # eval_result already has run_id set, so we can use it directly
        return self.create(
            run_id=eval_result.run_id,
            stage_num=eval_result.stage_num,
            stage_name=eval_result.stage_name,
            criterion_num=eval_result.criterion_num,
            criterion_type=eval_result.criterion_type,
            criterion_description=eval_result.criterion_description,
            score=eval_result.score,
            max_score=eval_result.max_score,
            feedback=eval_result.feedback,
            evaluated_action_ids=eval_result.evaluated_action_ids,
            evaluated_resource_ids=eval_result.evaluated_resource_ids,
        )


class TaskEvaluationResultsQueries(BaseQueries[TaskEvaluationResult]):
    """Query methods for TaskEvaluationResult model."""

    def __init__(self):
        super().__init__(TaskEvaluationResult)

    @staticmethod
    def get_by_run(run_id: UUID) -> TaskEvaluationResult | None:
        """Get task evaluation result for a run."""
        with next(get_session()) as session:
            statement = select(TaskEvaluationResult).where(TaskEvaluationResult.run_id == run_id)
            return session.exec(statement).first()  # type: ignore[attr-defined]


# Create query objects
class Queries:
    """Namespace for all query methods."""

    runs: RunsQueries
    experiments: ExperimentsQueries
    resources: ResourcesQueries
    messages: MessagesQueries
    actions: ActionsQueries
    evaluations: EvaluationsQueries
    criterion_results: CriterionResultsQueries
    task_evaluation_results: TaskEvaluationResultsQueries

    def __init__(self):
        self.runs = RunsQueries()
        self.experiments = ExperimentsQueries()
        self.resources = ResourcesQueries()
        self.messages = MessagesQueries()
        self.actions = ActionsQueries()
        self.evaluations = EvaluationsQueries()
        self.criterion_results = CriterionResultsQueries()
        self.task_evaluation_results = TaskEvaluationResultsQueries()


# Global queries instance
queries = Queries()
