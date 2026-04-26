"""ResearchGraphToolkit — run-scoped resource discovery for research workers.

Six pydantic-ai tools backed by ``ResourcesQueries`` and ``RunGraphEdge``
traversal so workers can enumerate their own, children's, and descendants'
resources, plus lookup by logical_path / content_hash.
"""

from collections.abc import Sequence
from uuid import UUID

from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.telemetry.models import RunResource

from ergon_builtins.tools.graph_toolkit_types import ResourceRef

try:
    from pydantic_ai.tools import Tool
except ImportError:  # pragma: no cover — defensive
    Tool = None  # type: ignore[assignment,misc]


class ResearchGraphToolkit:
    """Graph observability tools for run-scoped resource discovery.

    Constructor takes explicit IDs — no ``WorkerContext``.  The worker
    subclass unpacks context and passes them in (§7.3 pattern).
    """

    def __init__(self, *, run_id: UUID, task_execution_id: UUID) -> None:
        self._run_id = run_id
        self._task_execution_id = task_execution_id

    def build_tools(self) -> list["Tool"]:
        """Return the six resource-discovery tools for ``Agent(tools=[...])``."""
        if Tool is None:
            raise RuntimeError("pydantic-ai is required to build ResearchGraphToolkit tools")
        return [
            self._list_my_resources(),
            self._list_child_resources(),
            self._list_descendant_resources(),
            self._list_run_resources(),
            self._get_resource_by_logical_path(),
            self._get_resource_by_content_hash(),
        ]

    # ------------------------------------------------------------------
    # list_my_resources
    # ------------------------------------------------------------------

    def _list_my_resources(self) -> "Tool":
        run_id = self._run_id
        task_execution_id = self._task_execution_id

        async def list_my_resources() -> list[ResourceRef]:
            """List resources produced by my own task execution.

            Returns resources in most-recently-created-first order.
            Only resources belonging to this run are included.
            """
            rows = queries.resources.list_by_execution(task_execution_id)
            return _to_refs_sorted(
                [r for r in rows if r.run_id == run_id],
            )

        return Tool(function=list_my_resources, takes_ctx=False)

    # ------------------------------------------------------------------
    # list_child_resources
    # ------------------------------------------------------------------

    def _list_child_resources(self) -> "Tool":
        run_id = self._run_id
        task_execution_id = self._task_execution_id

        async def list_child_resources() -> list[ResourceRef]:
            """List resources produced by direct child task executions.

            Only returns resources from immediate children — not
            grandchildren or deeper descendants.
            """
            children = queries.task_executions.list_children_of(task_execution_id)
            result: list[RunResource] = []
            for child in children:
                rows = queries.resources.list_by_execution(child.id)
                result.extend(r for r in rows if r.run_id == run_id)
            return _to_refs_sorted(result)

        return Tool(function=list_child_resources, takes_ctx=False)

    # ------------------------------------------------------------------
    # list_descendant_resources
    # ------------------------------------------------------------------

    def _list_descendant_resources(self) -> "Tool":
        run_id = self._run_id
        task_execution_id = self._task_execution_id

        async def list_descendant_resources(
            max_depth: int = 3,
        ) -> list[ResourceRef]:
            """List resources from descendant task executions (BFS).

            Traverses child task executions up to *max_depth* levels deep,
            collecting all resources produced at each level.  Handles
            cycles gracefully via a visited set.

            Args:
                max_depth: Maximum depth of BFS traversal (default 3).
            """
            visited: set[UUID] = {task_execution_id}
            frontier: list[UUID] = [task_execution_id]
            result: list[RunResource] = []

            for _depth in range(max_depth):
                next_frontier: list[UUID] = []
                for parent_id in frontier:
                    children = queries.task_executions.list_children_of(
                        parent_id,
                    )
                    for child in children:
                        if child.id in visited:
                            continue
                        visited.add(child.id)
                        next_frontier.append(child.id)
                        rows = queries.resources.list_by_execution(child.id)
                        result.extend(r for r in rows if r.run_id == run_id)
                frontier = next_frontier
                if not frontier:
                    break

            return _to_refs_sorted(result)

        return Tool(function=list_descendant_resources, takes_ctx=False)

    # ------------------------------------------------------------------
    # list_run_resources
    # ------------------------------------------------------------------

    def _list_run_resources(self) -> "Tool":
        run_id = self._run_id

        async def list_run_resources() -> list[ResourceRef]:
            """List all resources in this run.

            Returns every resource row belonging to the current run,
            in most-recently-created-first order.
            """
            rows = queries.resources.list_by_run(run_id)
            return _to_refs_sorted(rows)

        return Tool(function=list_run_resources, takes_ctx=False)

    # ------------------------------------------------------------------
    # get_resource_by_logical_path
    # ------------------------------------------------------------------

    def _get_resource_by_logical_path(self) -> "Tool":
        run_id = self._run_id

        async def get_resource_by_logical_path(
            logical_path: str,
        ) -> ResourceRef | None:
            """Look up the latest resource by its logical path (file_path).

            Scoped to this run. Returns the most recently created resource
            with the given path, or null if none exists.

            Args:
                logical_path: The file_path of the resource to look up.
            """
            rows = queries.resources.list_by_run(run_id)
            matching = [r for r in rows if r.file_path == logical_path]
            if not matching:
                return None
            matching.sort(key=lambda r: (r.created_at, r.id), reverse=True)
            return ResourceRef.from_row(matching[0])

        return Tool(function=get_resource_by_logical_path, takes_ctx=False)

    # ------------------------------------------------------------------
    # get_resource_by_content_hash
    # ------------------------------------------------------------------

    def _get_resource_by_content_hash(self) -> "Tool":
        run_id = self._run_id

        async def get_resource_by_content_hash(
            content_hash: str,
        ) -> ResourceRef | None:
            """Look up the latest resource by its content hash.

            Scoped to this run. Returns the most recently created resource
            with the given hash, or null if none exists.

            Args:
                content_hash: The content hash to search for.
            """
            rows = queries.resources.list_by_run(run_id)
            matching = [r for r in rows if r.content_hash == content_hash]
            if not matching:
                return None
            matching.sort(key=lambda r: (r.created_at, r.id), reverse=True)
            return ResourceRef.from_row(matching[0])

        return Tool(function=get_resource_by_content_hash, takes_ctx=False)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_refs_sorted(rows: Sequence[RunResource]) -> list[ResourceRef]:
    """Convert ORM rows to ResourceRef DTOs, sorted created_at DESC."""
    sorted_rows = sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)
    return [ResourceRef.from_row(r) for r in sorted_rows]
