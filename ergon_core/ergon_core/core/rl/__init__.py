"""RL integration layer.

Provides the bridge between Ergon's Inngest-orchestrated environment
plane and external training frameworks (TRL, veRL).

Core components:

- ``extraction``: per-agent trajectory extraction from RunContextEvent rows
- ``rewards``: reward strategies for per-agent credit assignment
- ``rollout_service``: service client for managed rollout execution
"""

from ergon_core.api.json_types import JsonObject

LOGPROB_SETTINGS: JsonObject = {
    "openai_logprobs": True,
    "openai_top_logprobs": 1,
}
"""PydanticAI model settings that request logprobs from OpenAI-compatible APIs.

Only needed for the vLLM backend (which uses the OpenAI API format).
The transformers backend handles logprobs internally via output_logits.

Pass as ``model_settings`` when running the agent::

    result = await agent.run(prompt, model_settings=LOGPROB_SETTINGS)
"""
