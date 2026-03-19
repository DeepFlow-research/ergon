"""Unit tests for Task and Resource models."""

from pathlib import Path
from uuid import UUID, uuid4


from h_arcane import Resource, Task, TaskStatus
from h_arcane.core.worker import BaseWorker


# =============================================================================
# Mock Worker for Testing
# =============================================================================


class MockWorker(BaseWorker):
    """Simple mock worker for testing Task creation."""

    def __init__(self, name: str = "mock_worker"):
        self.id = uuid4()
        self.name = name
        self.model = "gpt-4o"
        self.tools = []
        self.system_prompt = "You are a test worker."

    async def execute(self, task, context):
        pass


# =============================================================================
# Resource Tests
# =============================================================================


class TestResource:
    """Tests for Resource model."""

    def test_resource_from_path(self):
        """Resource can be created from file path."""
        resource = Resource(path="data/report.xlsx", name="Quarterly Report")

        assert resource.path == "data/report.xlsx"
        assert resource.name == "Quarterly Report"
        assert resource.content is None
        assert resource.url is None

    def test_resource_mime_type_from_extension(self):
        """MIME type is derived from file extension."""
        xlsx = Resource(path="data/report.xlsx", name="Excel")
        pdf = Resource(path="docs/manual.pdf", name="PDF")
        txt = Resource(path="notes.txt", name="Text")
        json_res = Resource(path="config.json", name="JSON")

        assert xlsx.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert pdf.mime_type == "application/pdf"
        assert txt.mime_type == "text/plain"
        assert json_res.mime_type == "application/json"

    def test_resource_mime_type_override(self):
        """MIME type can be explicitly set."""
        resource = Resource(
            path="data/custom.bin",
            name="Binary",
            mime_type_override="application/octet-stream",
        )

        assert resource.mime_type == "application/octet-stream"

    def test_resource_from_content(self):
        """Resource can be created from inline content."""
        resource = Resource(name="Config", content='{"key": "value"}')

        assert resource.content == '{"key": "value"}'
        assert resource.path is None
        assert resource.mime_type == "text/plain"  # Default for content

    def test_resource_from_url(self):
        """Resource can be created from URL."""
        resource = Resource(name="Remote File", url="https://example.com/data.csv")

        assert resource.url == "https://example.com/data.csv"
        assert resource.path is None

    def test_resource_with_path_object(self):
        """Resource accepts Path objects."""
        resource = Resource(path=Path("data/report.xlsx"), name="Report")

        assert resource.path == Path("data/report.xlsx")
        assert (
            resource.mime_type
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============================================================================
# TaskStatus Tests
# =============================================================================


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values(self):
        """All expected status values exist."""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.READY == "ready"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_status_is_string(self):
        """TaskStatus values are strings."""
        assert isinstance(TaskStatus.PENDING, str)
        assert TaskStatus.COMPLETED == "completed"


# =============================================================================
# Task Creation Tests
# =============================================================================


class TestTaskCreation:
    """Tests for Task model creation."""

    def test_task_with_required_fields(self):
        """Task can be created with required fields."""
        worker = MockWorker()
        task = Task(
            name="Test Task",
            description="A test task",
            assigned_to=worker,
        )

        assert task.name == "Test Task"
        assert task.description == "A test task"
        assert task.assigned_to == worker
        assert isinstance(task.id, UUID)

    def test_task_auto_generates_id(self):
        """Task auto-generates UUID if not provided."""
        worker = MockWorker()
        task1 = Task(name="Task 1", description="First task", assigned_to=worker)
        task2 = Task(name="Task 2", description="Second task", assigned_to=worker)

        assert isinstance(task1.id, UUID)
        assert isinstance(task2.id, UUID)
        assert task1.id != task2.id

    def test_task_with_explicit_id(self):
        """Task accepts explicit UUID."""
        worker = MockWorker()
        explicit_id = uuid4()
        task = Task(id=explicit_id, name="Task", description="Test", assigned_to=worker)

        assert task.id == explicit_id

    def test_task_with_resources(self):
        """Task can have input resources."""
        worker = MockWorker()
        resources = [
            Resource(path="data.xlsx", name="Data"),
            Resource(path="config.json", name="Config"),
        ]
        task = Task(
            name="Task",
            description="Process the data files",
            assigned_to=worker,
            resources=resources,
        )

        assert len(task.resources) == 2
        assert task.resources[0].name == "Data"
        assert task.resources[1].name == "Config"

    def test_task_default_status_is_pending(self):
        """Task default status is PENDING."""
        worker = MockWorker()
        task = Task(name="Task", description="Test task", assigned_to=worker)

        assert task.status == TaskStatus.PENDING


# =============================================================================
# Task Properties Tests
# =============================================================================


class TestTaskProperties:
    """Tests for Task computed properties."""

    def test_is_leaf_for_task_without_children(self):
        """Task without children is a leaf."""
        worker = MockWorker()
        task = Task(name="Leaf", description="Atomic task", assigned_to=worker)

        assert task.is_leaf is True
        assert task.is_composite is False

    def test_is_composite_for_task_with_children(self):
        """Task with children is composite."""
        worker = MockWorker()
        child = Task(name="Child", description="Child task", assigned_to=worker)
        parent = Task(
            name="Parent", description="Parent task", assigned_to=worker, children=[child]
        )

        assert parent.is_leaf is False
        assert parent.is_composite is True

    def test_dependency_ids_with_task_objects(self):
        """dependency_ids resolves Task objects to UUIDs."""
        worker = MockWorker()
        dep1 = Task(name="Dep1", description="First dep", assigned_to=worker)
        dep2 = Task(name="Dep2", description="Second dep", assigned_to=worker)
        task = Task(
            name="Task", description="Main task", assigned_to=worker, depends_on=[dep1, dep2]
        )

        assert task.dependency_ids == [dep1.id, dep2.id]

    def test_dependency_ids_with_uuids(self):
        """dependency_ids passes through UUIDs unchanged."""
        worker = MockWorker()
        uuid1 = uuid4()
        uuid2 = uuid4()
        task = Task(name="Task", description="Test", assigned_to=worker, depends_on=[uuid1, uuid2])

        assert task.dependency_ids == [uuid1, uuid2]

    def test_dependency_ids_mixed(self):
        """dependency_ids handles mixed Task objects and UUIDs."""
        worker = MockWorker()
        dep_task = Task(name="Dep", description="Dependency", assigned_to=worker)
        dep_uuid = uuid4()
        task = Task(
            name="Task", description="Test", assigned_to=worker, depends_on=[dep_task, dep_uuid]
        )

        assert task.dependency_ids == [dep_task.id, dep_uuid]

    def test_effective_team_single_worker(self):
        """effective_team returns assigned_to when no full_team."""
        worker = MockWorker("main")
        task = Task(name="Task", description="Solo task", assigned_to=worker)

        assert task.effective_team == [worker]

    def test_effective_team_with_full_team(self):
        """effective_team returns full_team when specified."""
        main = MockWorker("main")
        helper1 = MockWorker("helper1")
        helper2 = MockWorker("helper2")
        task = Task(
            name="Task",
            description="Collaborative task",
            assigned_to=main,
            full_team=[main, helper1, helper2],
        )

        assert task.effective_team == [main, helper1, helper2]


# =============================================================================
# Task Hierarchy Tests
# =============================================================================


class TestTaskHierarchy:
    """Tests for Task hierarchy methods."""

    def test_get_all_descendants(self):
        """get_all_descendants returns all nested children."""
        worker = MockWorker()

        # Build tree:
        #     root
        #    /    \
        #   a      b
        #  / \
        # c   d

        c = Task(name="C", description="Task C", assigned_to=worker)
        d = Task(name="D", description="Task D", assigned_to=worker)
        a = Task(name="A", description="Task A", assigned_to=worker, children=[c, d])
        b = Task(name="B", description="Task B", assigned_to=worker)
        root = Task(name="Root", description="Root task", assigned_to=worker, children=[a, b])

        descendants = root.get_all_descendants()
        names = [t.name for t in descendants]

        assert len(descendants) == 4
        assert set(names) == {"A", "B", "C", "D"}

    def test_get_all_descendants_empty_for_leaf(self):
        """get_all_descendants returns empty list for leaf task."""
        worker = MockWorker()
        leaf = Task(name="Leaf", description="Leaf task", assigned_to=worker)

        assert leaf.get_all_descendants() == []

    def test_get_leaf_descendants(self):
        """get_leaf_descendants returns only leaf tasks."""
        worker = MockWorker()

        # Build tree (same as above)
        c = Task(name="C", description="Task C", assigned_to=worker)
        d = Task(name="D", description="Task D", assigned_to=worker)
        a = Task(name="A", description="Task A", assigned_to=worker, children=[c, d])
        b = Task(name="B", description="Task B", assigned_to=worker)
        root = Task(name="Root", description="Root task", assigned_to=worker, children=[a, b])

        leaves = root.get_leaf_descendants()
        names = [t.name for t in leaves]

        assert len(leaves) == 3  # B, C, D are leaves
        assert set(names) == {"B", "C", "D"}

    def test_get_leaf_descendants_returns_self_for_leaf(self):
        """get_leaf_descendants returns [self] for leaf task."""
        worker = MockWorker()
        leaf = Task(name="Leaf", description="Leaf task", assigned_to=worker)

        leaves = leaf.get_leaf_descendants()

        assert len(leaves) == 1
        assert leaves[0] == leaf
