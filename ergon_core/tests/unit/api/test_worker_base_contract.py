"""Contract tests for the base `Worker` field defaults.

PR 5 converted `Worker` from a hand-rolled ABC to a Pydantic `BaseModel`,
so the invariants now live on `Worker.model_fields[...]` rather than
the (auto-generated, kwargs-only) `__init__` signature.
"""

from pydantic_core import PydanticUndefined

from ergon_core.api import Worker


def test_model_field_has_no_default() -> None:
    """`model` must have no default value on the base.

    Defaults on worker config are an anti-pattern (RFC 2026-04-22):
    they hide sizing decisions. Factories must pass `model=` explicitly.
    """
    field = Worker.model_fields["model"]
    assert field.default is PydanticUndefined, (
        f"`model` must have no default; got {field.default!r}"
    )


def test_name_field_has_no_default() -> None:
    """Mirror of the `model` invariant: `name` also has no default on the base.

    Subclasses are free to override (e.g. ``TrainingStubWorker.name =
    "training-stub"``). The base contract is what's locked here so
    drift adding ``name = "worker"`` to ``ergon_core.api.worker.worker``
    is caught immediately.
    """
    field = Worker.model_fields["name"]
    assert field.default is PydanticUndefined, (
        f"`name` must have no default on the base Worker; got {field.default!r}"
    )
