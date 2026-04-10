"""Transformers backend: local HuggingFace model inference with logprob capture.

Resolves ``transformers:model-id`` targets to a PydanticAI Model that
runs inference locally via ``transformers.AutoModelForCausalLM``.
Extracts per-token logprobs from output logits for RL training.

Uses ``outlines`` for constrained JSON generation when PydanticAI
requests structured output (e.g. ``output_type`` on the Agent).
"""

import json as _json
import logging

import pydantic_ai.messages as _messages
import pydantic_ai.models as _models
from pydantic_ai.settings import ModelSettings
import torch
import outlines
from h_arcane.core.providers.generation.model_resolution import ResolvedModel

logger = logging.getLogger(__name__)


class TransformersModel(_models.Model):
    """PydanticAI Model backed by a local HuggingFace transformers model.

    Generates text, extracts per-token logprobs, and uses outlines for
    constrained JSON generation when structured output is requested.
    """

    def __init__(
        self,
        model_id: str,
        *,
        device: str = "cpu",
        torch_dtype: str = "float32",
        max_new_tokens: int = 512,
        policy_version: str | None = None,
    ):
        super().__init__()
        self._model_id = model_id
        self._device = device
        self._torch_dtype = torch_dtype
        self._max_new_tokens = max_new_tokens
        self._policy_version = policy_version
        self._hf_model = None
        self._hf_tokenizer = None
        self._outlines_model = None

    def _ensure_loaded(self) -> None:
        if self._hf_model is not None:
            return

        # reason: defer heavy deps until first use so importing this module does not load torch/transformers.
        import torch

        # reason: (same as torch above)
        from transformers import AutoModelForCausalLM, AutoTokenizer

        dtypes = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}

        logger.info("Loading transformers model: %s (device=%s)", self._model_id, self._device)
        dtype = dtypes.get(self._torch_dtype, torch.float32)
        self._hf_tokenizer = AutoTokenizer.from_pretrained(self._model_id)
        self._hf_model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            torch_dtype=dtype,
        ).to(self._device)
        self._hf_model.eval()

        if self._hf_tokenizer.pad_token is None:
            self._hf_tokenizer.pad_token = self._hf_tokenizer.eos_token

        logger.info(
            "Model loaded: %s (%d parameters)",
            self._model_id,
            sum(p.numel() for p in self._hf_model.parameters()),
        )

    @property
    def model_name(self) -> str:
        return f"transformers:{self._model_id}"

    @property
    def system(self) -> str:
        return "transformers"

    async def request(
        self,
        messages: list[_messages.ModelMessage],
        model_settings: ModelSettings | None = None,
        model_request_parameters: _models.ModelRequestParameters | None = None,
    ) -> _models.ModelResponse:
        """Generate a response with logprob extraction and optional JSON constraints."""
        self._ensure_loaded()

        prompt_text = self._messages_to_text(messages)
        json_schema = self._extract_output_schema(model_request_parameters)

        output_tool = self._extract_output_tool(model_request_parameters)

        if output_tool is not None:
            tool_schema = _json.dumps(output_tool.parameters_json_schema)
            response_text = self._generate_constrained(prompt_text, tool_schema)
            logprobs_list = self._compute_logprobs(prompt_text, response_text)
            return _models.ModelResponse(
                parts=[
                    _messages.ToolCallPart(
                        tool_name=output_tool.name,
                        args=_json.loads(response_text),
                        tool_call_id=f"call_{id(self)}",
                    )
                ],
                model_name=self.model_name,
                provider_details={"logprobs": logprobs_list},
            )

        if json_schema is not None:
            response_text = self._generate_constrained(prompt_text, json_schema)
        else:
            response_text = self._generate_unconstrained(prompt_text)

        logprobs_list = self._compute_logprobs(prompt_text, response_text)

        return _models.ModelResponse(
            parts=[_messages.TextPart(content=response_text)],
            model_name=self.model_name,
            provider_details={"logprobs": logprobs_list},
        )

    def _generate_unconstrained(self, prompt_text: str) -> str:
        """Generate text without constraints using model.generate()."""

        input_ids = self._hf_tokenizer.encode(prompt_text, return_tensors="pt").to(self._device)
        input_len = input_ids.shape[1]

        with torch.no_grad():
            outputs = self._hf_model.generate(
                input_ids,
                max_new_tokens=self._max_new_tokens,
                do_sample=True,
                temperature=0.7,
            )

        generated_ids = outputs[0, input_len:]
        return self._hf_tokenizer.decode(generated_ids, skip_special_tokens=True)

    def _generate_constrained(self, prompt_text: str, json_schema: str) -> str:
        """Generate JSON-constrained text using outlines."""
        try:
            if self._outlines_model is None:
                self._outlines_model = outlines.from_transformers(
                    self._hf_model,
                    self._hf_tokenizer,
                )

            gen = outlines.Generator(self._outlines_model, outlines.json_schema(json_schema))
            result = gen(prompt_text, max_new_tokens=self._max_new_tokens)
            logger.debug("Constrained generation produced %d chars", len(result))
            return result
        except ImportError:
            logger.warning("outlines not installed — falling back to unconstrained generation")
            return self._generate_unconstrained(prompt_text)
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            logger.warning("Constrained generation failed, falling back: %s", exc)
            return self._generate_unconstrained(prompt_text)

    def _compute_logprobs(self, prompt_text: str, response_text: str) -> list[dict]:
        """Compute per-token logprobs via a forward pass on the full sequence."""
        # reason: local import keeps torch import out of module load path for tests that mock the model.
        import torch

        full_text = prompt_text + response_text
        input_ids = self._hf_tokenizer.encode(full_text, return_tensors="pt").to(self._device)
        prompt_len = self._hf_tokenizer.encode(prompt_text, return_tensors="pt").shape[1]

        with torch.no_grad():
            outputs = self._hf_model(input_ids)
            logits = outputs.logits[0]

        logprobs_list = []
        for i in range(prompt_len, input_ids.shape[1]):
            token_id = input_ids[0, i].item()
            lp = torch.log_softmax(logits[i - 1], dim=-1)
            logprobs_list.append(
                {
                    "token": self._hf_tokenizer.decode([token_id]),
                    "logprob": lp[token_id].item(),
                }
            )

        return logprobs_list

    def _extract_output_tool(
        self,
        params: _models.ModelRequestParameters | None,
    ) -> _models.ToolDefinition | None:
        """Extract the output tool definition if PydanticAI is using tool mode for structured output."""
        if params is None:
            return None
        if params.output_mode == "tool" and params.output_tools:
            return params.output_tools[0]
        return None

    def _extract_output_schema(
        self,
        params: _models.ModelRequestParameters | None,
    ) -> str | None:
        """Extract JSON schema from PydanticAI request parameters if structured output is requested."""
        if params is None:
            return None

        if params.output_object is not None:
            return _json.dumps(params.output_object.json_schema)

        if params.output_tools:
            return _json.dumps(params.output_tools[0].parameters_json_schema)

        return None

    def _messages_to_text(self, messages: list[_messages.ModelMessage]) -> str:
        """Convert PydanticAI messages to a chat-template string."""
        chat_messages = []
        for msg in messages:
            if isinstance(msg, _messages.ModelRequest):
                for part in msg.parts:
                    if isinstance(part, _messages.SystemPromptPart):
                        chat_messages.append({"role": "system", "content": part.content})
                    elif isinstance(part, _messages.UserPromptPart):
                        chat_messages.append({"role": "user", "content": part.content})
                    elif isinstance(part, _messages.ToolReturnPart):
                        content = (
                            part.content if isinstance(part.content, str) else str(part.content)
                        )
                        chat_messages.append(
                            {"role": "tool", "content": content, "tool_call_id": part.tool_call_id}
                        )
            elif isinstance(msg, _messages.ModelResponse):
                for part in msg.parts:
                    if isinstance(part, _messages.TextPart):
                        chat_messages.append({"role": "assistant", "content": part.content})

        if not chat_messages:
            return ""

        try:
            return self._hf_tokenizer.apply_chat_template(
                chat_messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            logger.debug("apply_chat_template failed, using fallback: %s", exc)

        return "\n".join(m.get("content", "") for m in chat_messages)


def resolve_transformers(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``transformers:model-id`` target to a local model."""
    model_id = target[len("transformers:") :]
    model = TransformersModel(
        model_id=model_id,
        policy_version=policy_version,
    )
    logger.info("Resolved transformers model: %s", model_id)
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=True)
