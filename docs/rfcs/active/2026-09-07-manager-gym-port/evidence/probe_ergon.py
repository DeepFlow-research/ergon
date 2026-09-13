"""Characterize PydanticAI iteration nodes with Ergon's installed dependencies.

Run using Ergon's .venv/bin/python; no external model or Ergon services needed.
"""

import asyncio
import importlib.metadata
import json

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel


class Output(BaseModel):
    final_assistant_message: str


async def ping() -> str:
    return "pong"


async def main() -> None:
    agent = Agent(
        TestModel(call_tools=["ping"], custom_output_args={"final_assistant_message": "done"}),
        tools=[ping],
        output_type=Output,
    )
    async with agent.iter("test") as run:
        nodes = [type(node).__name__ async for node in run]
    print(json.dumps({"pydantic_ai_slim": importlib.metadata.version("pydantic-ai-slim"), "tool_calls": 1, "nodes": nodes}, indent=2))


asyncio.run(main())
