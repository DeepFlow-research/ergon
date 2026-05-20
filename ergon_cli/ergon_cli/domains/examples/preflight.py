import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from ergon_cli.domains.examples.models import ExampleCommand

LLAMA_SERVER_TEMPLATE = "llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 8080"
MODEL_DISCOVERY_TIMEOUT_SECONDS = 5


class ExampleSetupError(RuntimeError):
    """Raised when example prerequisites are not ready."""


@dataclass(frozen=True)
class PreflightResult:
    """Result of local model and sandbox setup checks."""

    discovered_model: str | None


def resolve_preflight_base_url(command: ExampleCommand) -> str:
    if command.model_target is None:
        return command.base_url or "http://localhost:8080"

    base_url = base_url_from_model_target(command.model_target)
    if base_url is None:
        raise ExampleSetupError(
            "--model-target must include an http(s) endpoint for this local llama.cpp example."
        )
    return base_url


def check_example_setup(command: ExampleCommand) -> PreflightResult:
    return preflight_llamacpp_and_e2b(base_url=resolve_preflight_base_url(command))


def preflight_llamacpp_and_e2b(*, base_url: str) -> PreflightResult:
    """Validate local llama.cpp and E2B setup without importing example files."""
    if not os.environ.get("E2B_API_KEY"):
        raise ExampleSetupError(
            "Missing E2B_API_KEY. Set it before launching so Ergon can create the Lean sandbox."
        )

    endpoint = base_url.rstrip("/")
    url = f"{endpoint}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read())
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ExampleSetupError(
            "Could not reach the llama.cpp server at "
            f"{url}. Start llama-server on that base URL, or pass --base-url."
        ) from exc

    model_id = _first_model_id(body)
    if model_id is None:
        raise ExampleSetupError(
            "The llama.cpp server responded, but /v1/models did not include a model id."
        )
    return PreflightResult(discovered_model=model_id)


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


def _first_model_id(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    models = body.get("data")
    if not isinstance(models, list):
        return None
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if isinstance(model_id, str) and model_id:
            return model_id
    return None
