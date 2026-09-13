"""Exercise MAG's provider wire contract through a real PydanticAI tool round trip."""

import json

import httpx
import pytest
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ergon_builtins.benchmarks.manager_gym import inference
from ergon_builtins.benchmarks.manager_gym.outputs import AITaskOutput
from ergon_builtins.llm.resolution import ResolvedModel


@pytest.mark.asyncio
async def test_final_json_preserves_tools_and_validates_retries(monkeypatch):
    requests, lookups = [], []
    final = {
        "reasoning": "Read the policy",
        "resources": [{"name": "Policy", "description": "Board approval", "content": "LARCH-6281"}],
        "confidence": 1.0,
        "execution_notes": [],
    }
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "lookup-1",
                    "type": "function",
                    "function": {"name": "lookup_policy", "arguments": "{}"},
                }
            ],
        },
        {"role": "assistant", "content": "{}"},
        {"role": "assistant", "content": json.dumps(final)},
    ]

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "response_format" not in body
        assert [m["role"] for m in body["messages"]].count("system") == 1
        assert body["messages"][0]["role"] == "system"
        assert "AITaskOutput" in body["messages"][0]["content"]
        assert [t["function"]["name"] for t in body["tools"]] == ["lookup_policy"]
        message = messages[len(requests) - 1]
        return httpx.Response(
            200,
            json={
                "id": "probe",
                "object": "chat.completion",
                "created": 0,
                "model": "qwen",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if "tool_calls" in message else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    async def lookup_policy() -> str:
        lookups.append(True)
        return "LARCH-6281"

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        backend = OpenAIChatModel(
            "qwen",
            provider=OpenAIProvider(
                base_url="https://model.invalid/v1", api_key="test", http_client=client
            ),
        )
        monkeypatch.setattr(
            inference, "resolve_model_target", lambda _: ResolvedModel(model=backend)
        )
        with override_allow_model_requests(True):
            result = await inference.infer(
                model=inference.INTERNAL_MODEL,
                system="Read the policy.",
                prompt="Create its resource.",
                output_type=AITaskOutput,
                tools=[lookup_policy],
            )
    assert len(requests) == 3 and lookups == [True]
    assert result.output["resources"][0]["content"] == "LARCH-6281"
    assert result.input_tokens == 30 and result.output_tokens == 15
    assert result.chunks
