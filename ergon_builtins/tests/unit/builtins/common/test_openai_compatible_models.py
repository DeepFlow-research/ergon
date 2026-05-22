"""OpenAI-compatible local model target resolution."""

import json
import urllib.request
from types import TracebackType

from pydantic_ai.models.openai import OpenAIChatModel

from ergon_builtins.llm.resolution import (
    registered_model_backend_prefixes,
    resolve_model_target,
)


class _FakeModelsResponse:
    def __init__(self, model_id: str) -> None:
        self._body = json.dumps({"data": [{"id": model_id}]}).encode()

    def __enter__(self) -> "_FakeModelsResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _patch_model_discovery(monkeypatch, model_id: str = "local-model") -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def fake_urlopen(url: str, timeout: int) -> _FakeModelsResponse:
        calls.append((url, timeout))
        return _FakeModelsResponse(model_id)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_openai_compatible_target_discovers_model_name(monkeypatch) -> None:
    calls = _patch_model_discovery(monkeypatch, "tinyllama-chat")

    resolved = resolve_model_target("openai-compatible:http://localhost:8080")

    assert isinstance(resolved.model, OpenAIChatModel)
    assert resolved.model.model_name == "tinyllama-chat"
    assert str(resolved.model.provider.client.base_url) == "http://localhost:8080/v1/"
    assert resolved.model.provider.client.api_key == "not-needed"
    assert resolved.supports_logprobs is True
    assert calls == [("http://localhost:8080/v1/models", 5)]


def test_llamacpp_alias_discovers_model_name_and_preserves_api_key(monkeypatch) -> None:
    calls = _patch_model_discovery(monkeypatch, "llama-cpp-model")

    resolved = resolve_model_target("llamacpp:http://localhost:8080", api_key="local-key")

    assert isinstance(resolved.model, OpenAIChatModel)
    assert resolved.model.model_name == "llama-cpp-model"
    assert str(resolved.model.provider.client.base_url) == "http://localhost:8080/v1/"
    assert resolved.model.provider.client.api_key == "local-key"
    assert calls == [("http://localhost:8080/v1/models", 5)]


def test_vllm_compatibility_alias_uses_openai_compatible_discovery(monkeypatch) -> None:
    calls = _patch_model_discovery(monkeypatch, "served-vllm-model")

    resolved = resolve_model_target("vllm:http://localhost:8000")

    assert isinstance(resolved.model, OpenAIChatModel)
    assert resolved.model.model_name == "served-vllm-model"
    assert str(resolved.model.provider.client.base_url) == "http://localhost:8000/v1/"
    assert resolved.model.provider.client.api_key == "not-needed"
    assert calls == [("http://localhost:8000/v1/models", 5)]


def test_explicit_model_name_skips_http_discovery(monkeypatch) -> None:
    def fail_urlopen(url: str, timeout: int) -> None:
        raise AssertionError(f"unexpected model discovery request: {url} {timeout}")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    resolved = resolve_model_target(
        "llamacpp:http://localhost:8080",
        model_name="explicit-local-model",
    )

    assert isinstance(resolved.model, OpenAIChatModel)
    assert resolved.model.model_name == "explicit-local-model"


def test_openai_compatible_backend_prefixes_are_registered() -> None:
    assert registered_model_backend_prefixes() >= {
        "llamacpp",
        "openai-compatible",
        "vllm",
    }
