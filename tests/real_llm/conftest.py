"""Session-level fixtures for the real-LLM tier.

Gates:
  - ERGON_REAL_LLM=1 must be set (else the entire tier skips).
  - OPENROUTER_API_KEY must be set (else real-LLM tests skip; stub canary
    continues to run if it opts in explicitly).
  - --assume-stack-up flag skips the docker-compose fixture and trusts the
    developer to have the stack running (pnpm dev:test + postgres + inngest
    + fastapi).

Session fixtures (docker stack, OpenRouter budget) live here; per-benchmark
fixtures live inside each test module.
"""

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--assume-stack-up",
        action="store_true",
        default=False,
        help="Skip docker-compose fixture; trust the developer to have the "
        "full stack (dashboard + backend + postgres + inngest) running.",
    )


@pytest.fixture(scope="session")
def real_llm_enabled() -> bool:
    return os.environ.get("ERGON_REAL_LLM") == "1"


@pytest.fixture(autouse=True)
def _skip_if_not_enabled(real_llm_enabled: bool, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("real_llm") and not real_llm_enabled:
        pytest.skip("ERGON_REAL_LLM=1 not set; real-LLM tier is opt-in")


# Re-export fixtures so pytest discovers them session-wide.
from tests.real_llm.fixtures.openrouter_budget import (  # noqa: E402, F401
    _maybe_enforce_budget,
    enforce_openrouter_budget,
    openrouter_budget,
)
from tests.real_llm.fixtures.harness_client import (  # noqa: E402, F401
    BackendHarnessClient,
    harness_client,
)
from tests.real_llm.fixtures.playwright_client import (  # noqa: E402, F401
    playwright_browser,
    playwright_context,
)
from tests.real_llm.fixtures.stack import real_llm_stack  # noqa: E402, F401
