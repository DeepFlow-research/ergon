"""
AgentRegistry - Collects and deduplicates workers from task trees.

The AgentRegistry is responsible for:
1. Walking a task tree and collecting all workers (assigned_to, full_team)
2. Deduplicating workers by their ID
3. Creating AgentConfig records for persistence
4. Mapping worker IDs to AgentConfig IDs after persistence
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from h_arcane.core._internal.db.models import AgentConfig
from h_arcane.core._internal.db.queries import queries

if TYPE_CHECKING:
    from h_arcane.core.task import Task
    from h_arcane.core.worker import BaseWorker


class AgentRegistry:
    """
    Collects and deduplicates workers from a task tree.

    Workers are collected from:
    - task.assigned_to (required for each task)
    - task.full_team (optional collaborators)

    Usage:
        # Collect workers from a task tree
        registry = AgentRegistry()
        registry.register_from_task(root_task)

        # Get all unique workers
        workers = registry.get_all_workers()

        # Persist to database (creates AgentConfig records)
        agent_configs = registry.persist(run_id)

        # Look up AgentConfig ID for a worker
        config_id = registry.get_config_id(worker.id)

    Attributes:
        workers: Mapping of worker_id → worker instance
    """

    def __init__(self):
        """Initialize an empty registry."""
        self.workers: dict[UUID, "BaseWorker"] = {}
        self._config_ids: dict[UUID, UUID] = {}  # worker_id -> AgentConfig.id
        self._persisted = False

    def register_from_task(self, task: "Task") -> None:
        """
        Recursively collect workers from a task tree.

        Walks the entire tree and registers:
        - task.assigned_to for each task
        - All workers in task.full_team (if present)

        Args:
            task: The root task (may have children)
        """
        # Register the assigned worker
        if task.assigned_to is not None:
            self.register_worker(task.assigned_to)

        # Register full team if present
        if task.full_team:
            for worker in task.full_team:
                self.register_worker(worker)

        # Recurse into children
        for child in task.children:
            self.register_from_task(child)

    def register_worker(self, worker: "BaseWorker") -> None:
        """
        Register a single worker (deduplicates by worker.id).

        Args:
            worker: Worker instance implementing BaseWorker protocol
        """
        worker_id = getattr(worker, "id", None)
        if worker_id is None:
            raise ValueError(f"Worker {worker} has no 'id' attribute")

        # Only add if not already registered
        if worker_id not in self.workers:
            self.workers[worker_id] = worker

    def get_all_workers(self) -> list["BaseWorker"]:
        """Get all registered workers."""
        return list(self.workers.values())

    def get_worker(self, worker_id: UUID) -> "BaseWorker" | None:
        """Get a worker by ID."""
        return self.workers.get(worker_id)

    def get_config_id(self, worker_id: UUID) -> UUID | None:
        """
        Get the AgentConfig ID for a worker.

        Only available after persist() has been called.

        Args:
            worker_id: The worker's UUID

        Returns:
            AgentConfig UUID, or None if not found/not persisted
        """
        return self._config_ids.get(worker_id)

    # === Data Creation (for testing without DB) ===

    def create_agent_config_data(
        self,
        worker: "BaseWorker",
        run_id: UUID,
        role: str = "worker",
    ) -> dict:
        """
        Convert a BaseWorker to AgentConfig data dict.

        This creates the data needed for an AgentConfig record
        but does not persist it. Useful for testing.

        Args:
            worker: Worker implementing BaseWorker protocol
            run_id: The run ID this config belongs to
            role: Agent role ("worker", "stakeholder", "manager")

        Returns:
            Dictionary suitable for creating an AgentConfig record
        """
        # Get tool names - handle both callable tools and string names
        tool_names = []
        for tool in getattr(worker, "tools", []):
            if hasattr(tool, "__name__"):
                tool_names.append(tool.__name__)
            elif hasattr(tool, "name"):
                tool_names.append(tool.name)
            elif isinstance(tool, str):
                tool_names.append(tool)
            else:
                tool_names.append(str(type(tool).__name__))

        return {
            "run_id": run_id,
            "name": getattr(worker, "name", "unknown"),
            "agent_type": type(worker).__name__,
            "model": getattr(worker, "model", "unknown"),
            "system_prompt": getattr(worker, "system_prompt", ""),
            "tools": tool_names,
            "role": role,
        }

    def create_all_agent_config_data(self, run_id: UUID) -> list[dict]:
        """
        Create AgentConfig data for all registered workers.

        Args:
            run_id: The run ID

        Returns:
            List of dicts suitable for creating AgentConfig records
        """
        return [
            self.create_agent_config_data(worker, run_id)
            for worker in self.workers.values()
        ]

    # === Persistence ===

    def persist(self, run_id: UUID) -> list["AgentConfig"]:
        """
        Create AgentConfig records for all registered workers.

        After calling this, get_config_id() can be used to look up
        the AgentConfig ID for any registered worker.

        Args:
            run_id: The run ID these configs belong to

        Returns:
            List of created AgentConfig records
        """
        created_configs: list[AgentConfig] = []

        for worker_id, worker in self.workers.items():
            config_data = self.create_agent_config_data(worker, run_id)
            config = AgentConfig(**config_data)
            created = queries.agent_configs.create(config)

            # Store mapping for later lookup
            self._config_ids[worker_id] = created.id
            created_configs.append(created)

        self._persisted = True
        return created_configs

    # === Utility ===

    def __len__(self) -> int:
        """Number of unique workers in the registry."""
        return len(self.workers)

    def __contains__(self, worker_id: UUID) -> bool:
        """Check if a worker ID is registered."""
        return worker_id in self.workers

    def __iter__(self):
        """Iterate over all workers."""
        return iter(self.workers.values())
