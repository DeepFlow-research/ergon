"""``SmokeWorkerBase._spec_for`` routes by slug; subclasses can override.

This is the hook that lets a sad-path subclass (Phase C) send one slug
(``l_2``) to a failing leaf while keeping the topology identical.
Tests cover:

- Default behaviour: every slug resolves to ``self.leaf_slug``.
- Subclass override: a dict-driven subclass routes specific slugs
  elsewhere without touching ``execute``.
"""

from typing import ClassVar
from uuid import uuid4

from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from ergon_core.test_support.smoke_fixtures.smoke_base.worker_base import SmokeWorkerBase


class _HappySubclass(SmokeWorkerBase):
    type_slug = "unit-test-happy"
    leaf_slug = "unit-test-leaf-happy"


class _RoutingSubclass(SmokeWorkerBase):
    """Sad-path pattern: route one slug to a failing leaf."""

    type_slug = "unit-test-routing"
    leaf_slug = "unit-test-leaf-happy"
    routing: ClassVar[dict[str, str]] = {"l_2": "unit-test-leaf-failing"}

    def _spec_for(self, slug, deps, desc):
        spec = super()._spec_for(slug, deps, desc)
        override = self.routing.get(slug)
        if override is None:
            return spec
        # Use model_copy to swap just the assigned_worker_slug; frozen model.
        return spec.model_copy(
            update={"assigned_worker_slug": AssignedWorkerSlug(override)},
        )


def _instance(cls):
    return cls(
        name="unit-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-unit",
    )


def test_default_spec_for_uses_leaf_slug() -> None:
    worker = _instance(_HappySubclass)
    spec = worker._spec_for("d_root", (), "Diamond root")
    assert spec.task_slug == TaskSlug("d_root")
    assert spec.description == "Diamond root"
    assert spec.assigned_worker_slug == AssignedWorkerSlug("unit-test-leaf-happy")
    assert spec.depends_on == []


def test_default_spec_for_propagates_deps() -> None:
    worker = _instance(_HappySubclass)
    spec = worker._spec_for("d_join", ("d_left", "d_right"), "Join")
    assert spec.depends_on == [TaskSlug("d_left"), TaskSlug("d_right")]


def test_routing_subclass_overrides_only_named_slug() -> None:
    worker = _instance(_RoutingSubclass)
    # Non-matching slug: default route
    d_root = worker._spec_for("d_root", (), "Root")
    assert d_root.assigned_worker_slug == AssignedWorkerSlug("unit-test-leaf-happy")
    # Matching slug: override
    l_2 = worker._spec_for("l_2", ("l_1",), "Line 2")
    assert l_2.assigned_worker_slug == AssignedWorkerSlug("unit-test-leaf-failing")
    # Dep + task_slug survive the override
    assert l_2.task_slug == TaskSlug("l_2")
    assert l_2.depends_on == [TaskSlug("l_1")]
