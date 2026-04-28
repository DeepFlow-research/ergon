import pytest

from ergon_core.core.dashboard.emitter import DashboardEmitter
from ergon_core.core.dashboard.provider import (
    get_dashboard_emitter,
    init_dashboard_emitter,
    reset_dashboard_emitter,
    set_dashboard_emitter,
)


def test_dashboard_emitter_provider_requires_startup_initialization() -> None:
    reset_dashboard_emitter()

    with pytest.raises(RuntimeError, match="DashboardEmitter has not been initialized"):
        get_dashboard_emitter()


def test_init_dashboard_emitter_installs_process_instance() -> None:
    reset_dashboard_emitter()

    emitter = init_dashboard_emitter(enabled=True)

    assert isinstance(emitter, DashboardEmitter)
    assert get_dashboard_emitter() is emitter


def test_set_dashboard_emitter_installs_injected_instance() -> None:
    reset_dashboard_emitter()
    emitter = DashboardEmitter(enabled=False)

    set_dashboard_emitter(emitter)

    assert get_dashboard_emitter() is emitter


def test_reset_dashboard_emitter_clears_process_instance() -> None:
    reset_dashboard_emitter()
    init_dashboard_emitter(enabled=True)

    reset_dashboard_emitter()

    with pytest.raises(RuntimeError, match="DashboardEmitter has not been initialized"):
        get_dashboard_emitter()
