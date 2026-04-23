"""``SmokeWorkerBase.execute`` is marked ``@final``.

Runtime guard — matches the static-type invariant ty/mypy enforce when
subclasses attempt to override ``execute``.  PEP 591 says ``typing.final``
sets ``__final__ = True`` on the decorated object at runtime; this test
asserts that marker is present.

If this test ever fails, the ``@final`` decorator was dropped from
``execute`` and smoke topology is no longer protected against subclass
drift.
"""

import pytest

from tests.e2e._fixtures.smoke_base.worker_base import SmokeWorkerBase


def test_execute_is_marked_final() -> None:
    assert getattr(SmokeWorkerBase.execute, "__final__", False) is True, (
        "SmokeWorkerBase.execute is no longer @final — smoke topology can "
        "be altered by subclass override. Restore @typing.final."
    )


def test_execute_decoration_survives_mro_lookup() -> None:
    """``@final`` is preserved through normal class-level attribute access.

    Belt-and-braces: we don't just check the unbound function; we also
    check the attribute accessed through the class, since that's how
    ty's static check resolves it.
    """
    resolved = SmokeWorkerBase.__dict__["execute"]
    assert getattr(resolved, "__final__", False) is True
