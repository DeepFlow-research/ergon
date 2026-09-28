"""Exercise MAG's provider wire contract through a real PydanticAI tool round trip."""

import asyncio
import json

import httpx
import pytest
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ergon_builtins.benchmarks.manager_gym import inference
from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile
from ergon_builtins.benchmarks.manager_gym.outputs import AITaskOutput
from ergon_builtins.llm.resolution import ResolvedModel

MODEL = "openai-compatible:http://localhost:8000/v1#test-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [True, "medium", 4.5])
async def test_judge_accepts_upstream_response_without_extra_confidence(monkeypatch, score):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from ergon_builtins.benchmarks.manager_gym.rubric import JudgeOutput

    calls = []

    def response(messages, info):
        calls.append(messages)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"reasoning": "Assessment of the supplied evidence", "score": score},
                )
            ]
        )

    monkeypatch.setattr(
        inference, "resolve_model_target", lambda _: ResolvedModel(model=FunctionModel(response))
    )
    with override_allow_model_requests(True):
        result = await inference.infer(
            model=MODEL,
            role="ai",
            profile=InferenceProfile(),
            system="You are a validation expert.",
            prompt="Evaluate the supplied fixture.",
            output_type=JudgeOutput,
        )
    assert len(calls) == 1
    assert result.output["score"] == score
    assert set(result.output) == {"reasoning", "score"}


@pytest.mark.asyncio
async def test_strict_output_preserves_tools_and_validates_retries(monkeypatch):
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
            "reasoning_content": "First inspect the policy, then produce its resource.",
            "tool_calls": [
                {
                    "id": "lookup-1",
                    "type": "function",
                    "function": {"name": "lookup_policy", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "final-bad",
                    "type": "function",
                    "function": {"name": "final_result", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "final-good",
                    "type": "function",
                    "function": {"name": "final_result", "arguments": json.dumps(final)},
                }
            ],
        },
    ]

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "response_format" not in body
        assert body["thinking_token_budget"] == 2048
        assert [m["role"] for m in body["messages"]].count("system") == 1
        assert body["messages"][0]["role"] == "system"
        assert body["tool_choice"] == "required"
        if len(requests) > 1:
            assistant = next(m for m in body["messages"] if m["role"] == "assistant")
            assert assistant["reasoning_content"] == messages[0]["reasoning_content"]
            acknowledgement = next(m for m in body["messages"] if m["role"] == "tool")
            assert acknowledgement["tool_call_id"] == "lookup-1"
            assert acknowledgement["content"] == "LARCH-6281"
        functions = {t["function"]["name"]: t["function"] for t in body["tools"]}
        assert set(functions) == {"lookup_policy", "final_result"}
        assert functions["final_result"]["strict"] is True
        assert set(functions["final_result"]["parameters"]["required"]) == set(final)
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
                model=MODEL,
                role="ai",
                profile=InferenceProfile(thinking_token_budget=2048),
                system="Read the policy.",
                prompt="Create its resource.",
                output_type=AITaskOutput,
                tools=[lookup_policy],
            )
    assert len(requests) == 3 and lookups == [True]
    assert result.output["resources"][0]["content"] == "LARCH-6281"
    assert result.input_tokens == 30 and result.output_tokens == 15
    assert result.chunks
    assert any(
        chunk.part.part_kind == "tool_result" and chunk.part.is_error for chunk in result.chunks
    )


@pytest.mark.asyncio
async def test_request_limit_retains_usage_and_tool_diagnostics(monkeypatch):
    from pydantic_ai.exceptions import UsageLimitExceeded
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    def response(messages, info):
        return ModelResponse(
            parts=[ToolCallPart("lookup_policy", {})],
            usage=RequestUsage(input_tokens=10, output_tokens=5),
        )

    async def lookup_policy() -> str:
        return "PRIVATE-POLICY-CONTENT"

    monkeypatch.setattr(
        inference, "resolve_model_target", lambda _: ResolvedModel(model=FunctionModel(response))
    )
    with override_allow_model_requests(True), pytest.raises(UsageLimitExceeded) as failed:
        await inference.infer(
            model=MODEL,
            role="ai",
            profile=InferenceProfile(),
            system="Private instructions",
            prompt="PRIVATE-PROMPT",
            output_type=AITaskOutput,
            tools=[lookup_policy],
        )
    note = failed.value.__notes__[0]
    responses = json.loads(note)["model_responses"]
    assert len(responses) == 12
    assert sum(r["input_tokens"] for r in responses) == 120
    assert sum(r["output_tokens"] for r in responses) == 60
    assert all(
        r["tools"] == [{"name": "lookup_policy", "arguments_characters": 2}] for r in responses
    )
    assert "PRIVATE" not in note
    with override_allow_model_requests(True):
        result = await inference.infer(
            model=MODEL,
            role="ai",
            profile=InferenceProfile(),
            system="Private instructions",
            prompt="PRIVATE-PROMPT",
            output_type=AITaskOutput,
            tools=[lookup_policy],
            accept_model_failure=True,
        )
    assert result.failure.kind == "request_limit"
    assert result.output == {}
    assert result.input_tokens == 120 and result.output_tokens == 60
    assert sum(c.part.part_kind == "tool_call" for c in result.chunks) == 12


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["validation", "http", "tool", "timeout"])
async def test_only_observed_model_behavior_becomes_a_work_outcome(monkeypatch, failure_kind):
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    errors = {
        "http": ModelHTTPError(503, "qwen", "unavailable"),
        "tool": RuntimeError("database unavailable"),
        "timeout": TimeoutError("request deadline"),
    }

    def response(messages, info):
        if failure_kind in errors:
            raise errors[failure_kind]
        return ModelResponse(parts=[ToolCallPart("final_result", {})])

    monkeypatch.setattr(
        inference, "resolve_model_target", lambda _: ResolvedModel(model=FunctionModel(response))
    )
    with override_allow_model_requests(True):
        operation = inference.infer(
            model=MODEL,
            role="ai",
            profile=InferenceProfile(),
            system="Create one resource.",
            prompt="Write a note.",
            output_type=AITaskOutput,
            accept_model_failure=True,
        )
        if failure_kind in errors:
            with pytest.raises(type(errors[failure_kind])):
                await operation
        else:
            result = await operation
            assert result.failure.kind == "output_validation"
            assert result.output == {}
            assert any(c.part.part_kind == "tool_result" and c.part.is_error for c in result.chunks)


@pytest.mark.asyncio
@pytest.mark.parametrize("work_role", [False, True])
async def test_native_work_lifetime_does_not_use_auxiliary_deadline(monkeypatch, work_role):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    timeout = asyncio.timeout

    # Scale the auxiliary deadline down; work must survive it, but must still
    # propagate an ordinary native cancellation while the model request is live.
    monkeypatch.setattr(
        inference.asyncio, "timeout", lambda seconds: timeout(0.001 if seconds else None)
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def response(messages, info):
        started.set()
        try:
            await asyncio.sleep(0.05)
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "final_result",
                        {
                            "reasoning": "done",
                            "resources": [],
                            "confidence": 1,
                            "execution_notes": [],
                        },
                    )
                ]
            )
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(
        inference, "resolve_model_target", lambda _: ResolvedModel(model=FunctionModel(response))
    )
    kwargs = dict(
        model=MODEL,
        role="ai",
        profile=InferenceProfile(),
        system="Work.",
        prompt="Work.",
        output_type=AITaskOutput,
        accept_model_failure=work_role,
    )
    with override_allow_model_requests(True):
        if work_role:
            result = await inference.infer(**kwargs)
            assert result.failure is None
            started.clear()
            task = asyncio.create_task(inference.infer(**kwargs))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set()
        else:
            with pytest.raises(TimeoutError):
                await inference.infer(**kwargs)


def test_profile_sends_thinking_budget_only_when_set():
    assert "extra_body" not in InferenceProfile().model_settings("ai")
    settings = InferenceProfile(thinking_token_budget=512).model_settings("human")
    assert settings["extra_body"] == {"thinking_token_budget": 512}
    assert settings["temperature"] == 0.7
    assert InferenceProfile().model_settings("decomposer")["temperature"] == 1
