from collections.abc import Iterator

import pytest
from ergon_core.core.infrastructure.dashboard.provider import (
    init_dashboard_emitter,
    reset_dashboard_emitter,
)


@pytest.fixture(autouse=True)
def dashboard_emitter_provider() -> Iterator[None]:
    reset_dashboard_emitter()
    init_dashboard_emitter(enabled=True)
    yield
    reset_dashboard_emitter()
