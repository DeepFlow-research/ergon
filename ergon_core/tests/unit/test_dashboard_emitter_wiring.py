"""Contract tests for the transport-only dashboard emitter."""

from __future__ import annotations

import inspect

from ergon_core.core.infrastructure.dashboard.emitter import DashboardEmitter


def test_dashboard_emitter_only_exposes_transport_publish() -> None:
    public_methods = {
        name
        for name, member in inspect.getmembers(DashboardEmitter, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == {"publish"}


def test_publish_is_async() -> None:
    assert inspect.iscoroutinefunction(DashboardEmitter.publish)
