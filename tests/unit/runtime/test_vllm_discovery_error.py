"""Tests for VLLMDiscoveryError and _discover_vllm_model_name."""

import json
import urllib.error
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Compatibility shim: the production module imports OpenAIChatModel from
# pydantic_ai.models.openai. Older installed versions expose only OpenAIModel.
# Force-import the pydantic_ai openai module first, then inject the missing
# name as a stub so that vllm_model.py can be imported cleanly.
# ---------------------------------------------------------------------------
import pydantic_ai.models.openai as _pai_openai  # noqa: E402

if not hasattr(_pai_openai, "OpenAIChatModel"):
    _pai_openai.OpenAIChatModel = type("OpenAIChatModel", (), {})  # type: ignore[attr-defined]

import pydantic_ai.providers.openai as _pai_providers_openai  # noqa: E402

if not hasattr(_pai_providers_openai, "OpenAIProvider"):
    _pai_providers_openai.OpenAIProvider = type("OpenAIProvider", (), {})  # type: ignore[attr-defined]

from ergon_core.core.providers.generation.vllm_model import (  # noqa: E402
    VLLMDiscoveryError,
    _discover_vllm_model_name,
)

_ENDPOINT = "http://localhost:8000"


def _mock_urlopen_returning(body_dict: dict):
    """Return a context manager that yields a response with the given JSON body."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body_dict).encode()
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=mock_resp)


def test_returns_first_model_name(monkeypatch):
    """Happy path: endpoint returns one model, name is returned."""
    monkeypatch.setattr(
        "ergon_core.core.providers.generation.vllm_model.urllib.request.urlopen",
        _mock_urlopen_returning({"data": [{"id": "my-model-v1"}]}),
    )
    result = _discover_vllm_model_name(_ENDPOINT)
    assert result == "my-model-v1"


def test_raises_on_url_error(monkeypatch):
    """Unreachable endpoint raises VLLMDiscoveryError, not URLError."""
    monkeypatch.setattr(
        "ergon_core.core.providers.generation.vllm_model.urllib.request.urlopen",
        MagicMock(side_effect=urllib.error.URLError("connection refused")),
    )
    with pytest.raises(VLLMDiscoveryError, match="connection refused"):
        _discover_vllm_model_name(_ENDPOINT)


def test_raises_on_empty_models_list(monkeypatch):
    """Endpoint with empty models list raises VLLMDiscoveryError."""
    monkeypatch.setattr(
        "ergon_core.core.providers.generation.vllm_model.urllib.request.urlopen",
        _mock_urlopen_returning({"data": []}),
    )
    with pytest.raises(VLLMDiscoveryError, match="no models"):
        _discover_vllm_model_name(_ENDPOINT)


def test_raises_when_model_missing_id(monkeypatch):
    """Model entry without 'id' field raises VLLMDiscoveryError."""
    monkeypatch.setattr(
        "ergon_core.core.providers.generation.vllm_model.urllib.request.urlopen",
        _mock_urlopen_returning({"data": [{"name": "no-id-field"}]}),
    )
    with pytest.raises(VLLMDiscoveryError, match="without a string 'id' field"):
        _discover_vllm_model_name(_ENDPOINT)
