"""Environment and preflight helpers for getting-started examples."""

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import cast

from ergon_core.core.shared.settings import settings
from pydantic import BaseModel, ConfigDict

DEFAULT_LLAMA_CPP_BASE_URL = "http://localhost:8080"
DEFAULT_MINIF2F_LIMIT = 3
DEFAULT_MINIF2F_MAX_ITERATIONS = 12
MODEL_DISCOVERY_TIMEOUT_SECONDS = 5


class ExampleSetupError(RuntimeError):
    """Raised when a common local setup requirement is missing."""


class PreflightResult(BaseModel):
    """Result of local model and sandbox setup checks."""

    model_config = ConfigDict(frozen=True)

    discovered_model: str | None


def env_str(name: str, default: str, environ: Mapping[str, str] | None = None) -> str:
    """Read a string environment default."""
    source = environ if environ is not None else os.environ
    value = source.get(name)
    return value if value not in (None, "") else default


def env_optional_str(name: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Read an optional string environment default."""
    source = environ if environ is not None else os.environ
    value = source.get(name)
    return value if value not in (None, "") else None


def env_positive_int(name: str, default: int, environ: Mapping[str, str] | None = None) -> int:
    """Read a positive integer environment default."""
    source = environ if environ is not None else os.environ
    raw = source.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ExampleSetupError(f"{name} must be a positive integer, got {raw!r}.") from exc
    if value < 1:
        raise ExampleSetupError(f"{name} must be a positive integer, got {raw!r}.")
    return value


def build_llamacpp_model_target(
    *,
    base_url: str,
    model_name: str | None = None,
    model_target: str | None = None,
) -> str:
    """Build the Ergon model target string for a llama.cpp server."""
    if model_target:
        return model_target

    endpoint = base_url.rstrip("/")
    if not endpoint:
        raise ExampleSetupError("llama.cpp base URL cannot be empty.")
    if model_name:
        return f"llamacpp:{endpoint}#{model_name}"
    return f"llamacpp:{endpoint}"


def base_url_from_model_target(model_target: str) -> str | None:
    """Return the URL endpoint from an OpenAI-compatible Ergon model target."""
    _prefix, separator, rest = model_target.partition(":")
    if not separator:
        return None
    endpoint, _model_separator, _model_name = rest.partition("#")
    endpoint = endpoint.rstrip("/")
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return None


def preflight_llamacpp_and_e2b(*, base_url: str) -> PreflightResult:
    """Fail fast for the two most common MiniF2F local setup misses."""
    if not settings.e2b_api_key:
        raise ExampleSetupError(
            "Missing E2B_API_KEY. Set it in Ergon's .env file or process environment "
            "before launching so Ergon can create the Lean sandbox."
        )

    model_id = discover_llamacpp_model(
        base_url=base_url,
        timeout_seconds=MODEL_DISCOVERY_TIMEOUT_SECONDS,
    )
    return PreflightResult(discovered_model=model_id)


def discover_llamacpp_model(*, base_url: str, timeout_seconds: float) -> str:
    """Poll a llama.cpp OpenAI-compatible server until it reports a model id."""
    endpoint = base_url.rstrip("/")
    url = f"{endpoint}/v1/models"
    deadline = time.monotonic() + timeout_seconds
    last_error: BaseException | None = None
    while time.monotonic() <= deadline:
        try:
            with urllib.request.urlopen(url, timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read())
            model_id = _first_model_id(body)
            if model_id is not None:
                return model_id
            raise ExampleSetupError(
                "The llama.cpp server responded, but /v1/models did not include a model id."
            )
        except ExampleSetupError:
            raise
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            time.sleep(0.5)

    raise ExampleSetupError(
        "Could not reach the llama.cpp server at "
        f"{url}. Start llama-server on that base URL, or pass --base-url."
    ) from last_error


def _first_model_id(body: object) -> str | None:
    if not isinstance(body, Mapping):
        return None
    mapping = cast(Mapping[str, object], body)
    models = mapping.get("data")
    if not isinstance(models, list):
        return None
    for model in models:
        if not isinstance(model, Mapping):
            continue
        model_mapping = cast(Mapping[str, object], model)
        model_id = model_mapping.get("id")
        if isinstance(model_id, str) and model_id:
            return model_id
    return None
