"""
Conftest for unit tests.

Unit tests don't require database connectivity or external services.
This conftest overrides the session-scoped fixtures from the parent conftest
to prevent database connection attempts.
"""

import pytest


# Override the autouse session fixture to prevent DB cleanup
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """No-op fixture for unit tests - we don't need DB setup."""
    yield


@pytest.fixture(scope="session")
def db_engine():
    """No-op fixture for unit tests - we don't need a DB engine."""
    yield None


@pytest.fixture
def db_session():
    """No-op fixture for unit tests - we don't need DB sessions."""
    yield None
