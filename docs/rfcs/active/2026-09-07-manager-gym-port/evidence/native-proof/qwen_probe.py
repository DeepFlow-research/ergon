"""Bounded standing-deployment probe; credentials are never included in evidence."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import dotenv_values
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from ergon_builtins.llm.resolution import resolve_model_target

MODEL = "qwen3-8-27b-28"
BASE = f"https://api.training.hcompany.ai/v1/models/{MODEL}"
OUT = Path(__file__).with_name("qwen-result.json")


class Decision(BaseModel):
    actor: Literal["alice"]
    fatigue: float


async def main() -> None:
    key = os.environ.get("HAI_API_KEY")
    if not key and os.environ.get("MAG_PROOF_SECRET_FILE"):
        key = dotenv_values(os.environ["MAG_PROOF_SECRET_FILE"]).get("HAI_API_KEY")
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "deployment": MODEL,
        "base_url": BASE,
        "credential_present": bool(key),
    }
    if not key:
        OUT.write_text(json.dumps(result, indent=2))
        return
    async with httpx.AsyncClient(timeout=20, headers={"Authorization": f"Bearer {key}"}) as client:
        for label, path in (
            ("health", "/health"),
            ("native_models_route", "/models"),
            ("ergon_models_route", "/v1/models"),
        ):
            try:
                response = await client.get(BASE + path)
                result[label] = {"status": response.status_code}
                if label.endswith("models_route") and response.is_success:
                    result[label]["model_ids"] = [
                        item.get("id") for item in response.json().get("data", [])
                    ]
            except Exception as exc:
                result[label] = {"error_type": type(exc).__name__}
    models = {
        "existing_ergon_resolver": resolve_model_target(
            f"openai-compatible:{BASE}#{MODEL}", api_key=key
        ).model,
        "direct_provider_control": OpenAIChatModel(
            MODEL,
            provider=OpenAIProvider(
                openai_client=AsyncOpenAI(base_url=BASE, api_key=key, timeout=45, max_retries=0)
            ),
        ),
    }
    for label, model in models.items():
        calls = []

        def read_fatigue(actor: str) -> float:
            """Read the fatigue of the named actor from the synthetic proof fixture."""
            calls.append(actor)
            return 0.25

        agent = Agent(
            model,
            output_type=Decision,
            tools=[read_fatigue],
            retries=0,
            instructions="Use read_fatigue for alice, then return alice and that exact fatigue. Keep reasoning brief.",
            model_settings={
                "max_tokens": 1024,
                "temperature": 0,
                "timeout": 45,
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
            },
        )
        try:
            run = await asyncio.wait_for(
                agent.run(
                    "Read alice's fatigue and return the structured decision.",
                    usage_limits=UsageLimits(request_limit=3),
                ),
                timeout=100,
            )
            result[label] = {
                "output": run.output.model_dump(),
                "tool_calls": calls,
                "usage": str(run.usage()),
                "passed": calls == ["alice"] and run.output.fatigue == 0.25,
            }
        except Exception as exc:
            result[label] = {
                "error_type": type(exc).__name__,
                "status": getattr(exc, "status_code", None),
                "tool_calls": calls,
            }
        OUT.write_text(json.dumps(result, indent=2))
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
