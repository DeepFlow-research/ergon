"""Database query methods organized by entity."""

from uuid import UUID
from typing import TypeVar, Generic, Type
from sqlmodel import SQLModel, select, desc
from datetime import datetime, timezone

from h_arcane.core.db.connection import get_session
from h_arcane.core.db.models import (
    AgentConfig,
    Experiment,
    Run,
    RunStatus,
    Message,
    Action,
    Resource,
    Evaluation,
    CriterionResult,
    TaskEvaluationResult,
    Thread,
    ThreadMessage,
)
from h_arcane.benchmarks.enums import BenchmarkName


T = TypeVar("T", bound=SQLModel)


class BaseQueries(Generic[T]):
    """Base query class with common CRUD operations."""

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, id: UUID) -> T | None:
        """Get entity by ID."""
        with next(get_session()) as session:
            return session.get(self.model, id)

    def create(self, entity: T) -> T:
        """Create a new entity from a typed object."""
        # Validate and create new instance without id (will be auto-generated)
        entity_data = entity.model_dump(exclude={"id"}, exclude_none=False)
        new_entity = self.model.model_validate(entity_data)
        with next(get_session()) as session:
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)
            return new_entity

    def update(self, entity: T) -> T:
        """Update entity fields from a typed object."""
        # Check if entity has id attribute (all SQLModel tables should have it)
        entity_id = getattr(entity, "id", None)
        if entity_id is None:
            raise ValueError(f"{self.model.__name__} id must be set for update")
        with next(get_session()) as session:
            existing = session.get(self.model, entity_id)
            if existing is None:
                raise ValueError(f"{self.model.__name__} {entity_id} not found")
            # Merge updates: preserve unset fields, update set fields
            update_data = entity.model_dump(exclude_none=True)
            # Copy updated fields back to existing entity for SQLAlchemy tracking
            for key, value in update_data.items():
                setattr(existing, key, value)
            session.commit()
            session.refresh(existing)
            return existing


class RunsQueries(BaseQueries[Run]):
    """Query methods for Run model."""

    def __init__(self):
        super().__init__(Run)

    @staticmethod
    def get_by_status(status: RunStatus) -> list[Run]:
        """Get all runs with given status."""
        with next(get_session()) as session:
            statement = select(Run).where(Run.status == status)
            return list(session.exec(statement).all())

    @staticmethod
    def get_stats() -> dict:
        """Get run statistics."""
        with next(get_session()) as session:
            total = session.exec(select(Run)).all()
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
        existing = self.get(run_id)
        if existing is None:
            raise ValueError(f"Run {run_id} not found")
        updated = existing.model_copy(
            update={
                "status": RunStatus.PENDING,
                "error_message": None,
                "started_at": None,
                "completed_at": None,
            }
        )
        return self.update(updated)


class ExperimentsQueries(BaseQueries[Experiment]):
    """Query methods for Experiment model."""

    def __init__(self):
        super().__init__(Experiment)

    @staticmethod
    def get_by_task_id(task_id: str, benchmark_name: BenchmarkName) -> Experiment:
        """Get experiment by task ID and benchmark."""
        with next(get_session()) as session:
            statement = select(Experiment).where(
                Experiment.benchmark_name == benchmark_name, Experiment.task_id == task_id
            )
            result = session.exec(statement).first()
            if result is None:
                raise ValueError(f"Experiment not found: {benchmark_name.value}/{task_id}")
            return result


class ResourcesQueries(BaseQueries[Resource]):
    """Query methods for Resource model."""

    def __init__(self):
        super().__init__(Resource)

    @staticmethod
    def get_by_experiment(experiment_id: UUID) -> list[Resource]:
        """Get all input resources for an experiment."""
        with next(get_session()) as session:
            statement = select(Resource).where(Resource.experiment_id == experiment_id)
            return list(session.exec(statement).all())

    @staticmethod
    def get_by_run(run_id: UUID) -> list[Resource]:
        """Get all output resources for a run."""
        with next(get_session()) as session:
            statement = select(Resource).where(Resource.run_id == run_id)
            return list(session.exec(statement).all())

    @staticmethod
    def get_all(run_id: UUID | None = None, experiment_id: UUID | None = None) -> list[Resource]:
        """Get all resources, optionally filtered by run_id or experiment_id."""
        with next(get_session()) as session:
            statement = select(Resource)
            if run_id:
                statement = statement.where(Resource.run_id == run_id)
            if experiment_id:
                statement = statement.where(Resource.experiment_id == experiment_id)
            return list(session.exec(statement).all())


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
                statement = statement.order_by("sequence_num")
            return list(session.exec(statement).all())


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
                statement = statement.order_by("action_num")
            return list(session.exec(statement).all())


class EvaluationsQueries(BaseQueries[Evaluation]):
    """Query methods for Evaluation model."""

    def __init__(self):
        super().__init__(Evaluation)

    @staticmethod
    def get_by_run(run_id: UUID) -> Evaluation | None:
        """Get evaluation for a run."""
        with next(get_session()) as session:
            statement = select(Evaluation).where(Evaluation.run_id == run_id)
            return session.exec(statement).first()

    def create_from_eval(
        self,
        run_id: UUID,
        eval_result: Evaluation,
    ) -> Evaluation:
        """Create or update Evaluation from evaluation model (idempotent)."""
        # Check if evaluation already exists for this run_id
        existing = self.get_by_run(run_id)

        if existing:
            # Update existing evaluation - merge updates excluding id and run_id
            update_data = eval_result.model_dump(exclude={"id", "run_id"}, exclude_none=True)
            updated = existing.model_copy(update=update_data)
            updated.id = existing.id  # Preserve existing id
            updated.run_id = existing.run_id  # Preserve existing run_id
            return self.update(updated)
        else:
            # Create new evaluation - validate and exclude id
            entity_data = eval_result.model_dump(exclude={"id"}, exclude_none=False)
            new_eval = self.model.model_validate(entity_data)
            return self.create(new_eval)


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
                        statement = statement.order_by(field_attr)
            return list(session.exec(statement).all())

    def create_from_eval(
        self,
        run_id: UUID,
        eval_result: CriterionResult,
    ) -> CriterionResult:
        """Create CriterionResult from evaluation model."""
        # Validate and exclude id - eval_result already has run_id set
        entity_data = eval_result.model_dump(exclude={"id"}, exclude_none=False)
        new_criterion = self.model.model_validate(entity_data)
        return self.create(new_criterion)


class TaskEvaluationResultsQueries(BaseQueries[TaskEvaluationResult]):
    """Query methods for TaskEvaluationResult model."""

    def __init__(self):
        super().__init__(TaskEvaluationResult)

    @staticmethod
    def get_by_run(run_id: UUID) -> TaskEvaluationResult | None:
        """Get task evaluation result for a run."""
        with next(get_session()) as session:
            statement = select(TaskEvaluationResult).where(TaskEvaluationResult.run_id == run_id)
            return session.exec(statement).first()


class AgentConfigsQueries(BaseQueries[AgentConfig]):
    """Query methods for AgentConfig model."""

    def __init__(self):
        super().__init__(AgentConfig)

    @staticmethod
    def get_by_run(run_id: UUID) -> list[AgentConfig]:
        """Get all agent configs for a run."""
        with next(get_session()) as session:
            statement = select(AgentConfig).where(AgentConfig.run_id == run_id)
            return list(session.exec(statement).all())


# =============================================================================
# Communication Service Queries
# =============================================================================


class ThreadsQueries(BaseQueries[Thread]):
    """Query methods for Thread model."""

    def __init__(self):
        super().__init__(Thread)

    @staticmethod
    def _normalize_agent_ids(agent_a_id: str, agent_b_id: str) -> tuple[str, str]:
        """Normalize agent IDs to consistent order (smaller, larger)."""
        if agent_a_id < agent_b_id:
            return agent_a_id, agent_b_id
        return agent_b_id, agent_a_id

    def get_or_create_thread(
        self,
        run_id: UUID,
        experiment_id: UUID,
        agent_a_id: str,
        agent_b_id: str,
        topic: str,
    ) -> Thread:
        """Get existing thread or create new one."""
        normalized_a, normalized_b = self._normalize_agent_ids(agent_a_id, agent_b_id)

        with next(get_session()) as session:
            statement = select(Thread).where(
                Thread.run_id == run_id,
                Thread.agent_a_id == normalized_a,
                Thread.agent_b_id == normalized_b,
                Thread.topic == topic,
            )
            existing = session.exec(statement).first()

            if existing:
                return existing

            # Create new thread
            new_thread = Thread(
                run_id=run_id,
                experiment_id=experiment_id,
                agent_a_id=normalized_a,
                agent_b_id=normalized_b,
                topic=topic,
            )
            session.add(new_thread)
            session.commit()
            session.refresh(new_thread)
            return new_thread

    def get_threads_between_agents(
        self,
        agent_a_id: str,
        agent_b_id: str,
    ) -> list[Thread]:
        """Get all threads between two agents."""
        normalized_a, normalized_b = self._normalize_agent_ids(agent_a_id, agent_b_id)

        with next(get_session()) as session:
            statement = (
                select(Thread)
                .where(
                    Thread.agent_a_id == normalized_a,
                    Thread.agent_b_id == normalized_b,
                )
                .order_by(desc(Thread.updated_at))
            )
            return list(session.exec(statement).all())

    def update_timestamp(self, thread_id: UUID) -> Thread:
        """Update the updated_at timestamp of a thread."""
        with next(get_session()) as session:
            thread = session.get(Thread, thread_id)
            if thread is None:
                raise ValueError(f"Thread {thread_id} not found")
            thread.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(thread)
            return thread


class ThreadMessagesQueries(BaseQueries[ThreadMessage]):
    """Query methods for ThreadMessage model."""

    def __init__(self):
        super().__init__(ThreadMessage)

    def get_by_thread(
        self,
        thread_id: UUID,
        order_by: str = "sequence_num",
    ) -> list[ThreadMessage]:
        """Get all messages in a thread, ordered by sequence."""
        with next(get_session()) as session:
            statement = select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
            if order_by == "sequence_num":
                statement = statement.order_by("sequence_num")
            return list(session.exec(statement).all())

    def get_next_sequence_num(self, thread_id: UUID) -> int:
        """Get the next sequence number for a thread."""
        with next(get_session()) as session:
            statement = (
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread_id)
                .order_by(desc(ThreadMessage.sequence_num))
            )
            last_message = session.exec(statement).first()
            return (last_message.sequence_num + 1) if last_message else 0

    def create_message(
        self,
        thread_id: UUID,
        run_id: UUID,
        experiment_id: UUID,
        from_agent_id: str,
        to_agent_id: str,
        content: str,
    ) -> ThreadMessage:
        """Create a new message in a thread."""
        sequence_num = self.get_next_sequence_num(thread_id)

        new_message = ThreadMessage(
            thread_id=thread_id,
            run_id=run_id,
            experiment_id=experiment_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            content=content,
            sequence_num=sequence_num,
        )
        return self.create(new_message)

    def count_by_thread(self, thread_id: UUID) -> int:
        """Count the number of messages in a thread."""
        with next(get_session()) as session:
            statement = select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
            return len(session.exec(statement).all())


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
    agent_configs: AgentConfigsQueries
    threads: ThreadsQueries
    thread_messages: ThreadMessagesQueries

    def __init__(self):
        self.runs = RunsQueries()
        self.experiments = ExperimentsQueries()
        self.resources = ResourcesQueries()
        self.messages = MessagesQueries()
        self.actions = ActionsQueries()
        self.evaluations = EvaluationsQueries()
        self.criterion_results = CriterionResultsQueries()
        self.task_evaluation_results = TaskEvaluationResultsQueries()
        self.agent_configs = AgentConfigsQueries()
        self.threads = ThreadsQueries()
        self.thread_messages = ThreadMessagesQueries()


# Global queries instance
queries = Queries()
