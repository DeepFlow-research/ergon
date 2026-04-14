"""
Spike: vLLM logprob splitting across ModelResponse parts.

QUESTION
--------
When vLLM (via OpenAI-compatible API) generates a response that PydanticAI
splits into multiple parts (TextPart + ToolCallPart, or ThinkingPart + TextPart),
does choice.logprobs.content contain tokens for ALL parts, or only the text content?

If all tokens are present in the flat logprob list, we can reconstruct part
boundaries by matching token strings against each part's content string.

WHAT THIS SPIKE DOES
--------------------
1. Constructs mock OpenAI API response objects that mirror what vLLM returns.
2. Runs them through the PydanticAI OpenAI model parsing logic to produce
   ModelResponse + vendor_details.
3. Shows exactly what ends up in provider_details["logprobs"] for:
   - Scenario A: text-only response
   - Scenario B: tool-call-only response (no text)
   - Scenario C: text + tool call in same response
   - Scenario D: thinking + tool call (extended thinking)
4. Tests the boundary-reconstruction algorithm: join token strings → match
   against part content → split logprob list.

USAGE
-----
    uv run python scripts/spike_logprob_splitting.py

The script uses two approaches:
  [MOCK]  Constructs synthetic responses to test the splitting algorithm.
          This always runs.
  [LIVE]  Makes a real vLLM call if VLLM_BASE_URL is set in the environment.
          This verifies whether vLLM actually includes tool call tokens in
          choice.logprobs.content.

KEY UNKNOWN (what we're trying to determine)
--------------------------------------------
Standard OpenAI API: choice.logprobs.content contains ONLY content tokens.
                     Tool call argument tokens have NO logprobs in this field.
vLLM behaviour:      Unknown — vLLM generates one forward pass then splits.
                     It MAY include tool call tokens in logprobs.content.

The [LIVE] path answers this definitively.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Minimal mock types mirroring the openai library's response objects.
# We only need enough structure to test the PydanticAI parsing path and our
# splitting algorithm — no real HTTP calls.
# ---------------------------------------------------------------------------


@dataclass
class MockTopLogprob:
    token: str
    logprob: float
    bytes: list[int] | None = None


@dataclass
class MockTokenLogprob:
    token: str
    logprob: float
    bytes: list[int] | None = None
    top_logprobs: list[MockTopLogprob] | None = None


@dataclass
class MockLogprobs:
    content: list[MockTokenLogprob]


@dataclass
class MockFunction:
    name: str
    arguments: str  # JSON string


@dataclass
class MockToolCall:
    id: str
    type: str
    function: MockFunction


@dataclass
class MockMessage:
    content: str | None
    tool_calls: list[MockToolCall] | None
    role: str = "assistant"


@dataclass
class MockChoice:
    message: MockMessage
    logprobs: MockLogprobs | None
    finish_reason: str
    index: int = 0


def _tokenise_string(text: str) -> list[MockTokenLogprob]:
    """
    Fake tokeniser: splits text into ~4-char chunks, each assigned a
    synthetic logprob. Real token boundaries differ by model/vocab but
    this is sufficient to test the splitting algorithm structure.
    """
    tokens: list[MockTokenLogprob] = []
    i = 0
    lp = -0.05
    while i < len(text):
        chunk = text[i : i + 4]
        tokens.append(MockTokenLogprob(token=chunk, logprob=lp))
        lp -= 0.05
        i += 4
    return tokens


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------


def scenario_a_text_only() -> tuple[MockChoice, str]:
    """Text-only response. Baseline — should always have correct logprobs."""
    text = "The capital of France is Paris."
    tokens = _tokenise_string(text)
    choice = MockChoice(
        message=MockMessage(content=text, tool_calls=None),
        logprobs=MockLogprobs(content=tokens),
        finish_reason="stop",
    )
    return choice, "text-only"


def scenario_b_tool_call_only() -> tuple[MockChoice, str]:
    """
    Tool call only — NO text content.

    Standard OpenAI API: logprobs.content is empty (no content tokens).
    vLLM hypothesis:     logprobs.content MAY contain the tool call arg tokens
                         because vLLM generates them in the same forward pass.

    We model BOTH sub-cases:
    B1: vLLM includes tool call tokens in logprobs.content (optimistic case)
    B2: logprobs.content is empty (standard OpenAI behaviour)
    """
    args = '{"query": "Paris population"}'
    tool_tokens = _tokenise_string(args)

    # B1 — vLLM puts tool call arg tokens in logprobs.content
    choice_b1 = MockChoice(
        message=MockMessage(
            content=None,
            tool_calls=[MockToolCall(id="call_001", type="function",
                                     function=MockFunction(name="search", arguments=args))],
        ),
        logprobs=MockLogprobs(content=tool_tokens),  # hypothesis: vLLM includes these
        finish_reason="tool_calls",
    )

    # B2 — standard OpenAI: logprobs.content is empty for tool-call-only responses
    choice_b2 = MockChoice(
        message=MockMessage(
            content=None,
            tool_calls=[MockToolCall(id="call_001", type="function",
                                     function=MockFunction(name="search", arguments=args))],
        ),
        logprobs=MockLogprobs(content=[]),  # standard OpenAI behaviour
        finish_reason="tool_calls",
    )

    return (choice_b1, "tool-call-only [vLLM hypothesis: tokens in logprobs.content]",
            choice_b2, "tool-call-only [OpenAI standard: empty logprobs.content]")  # type: ignore[return-value]


def scenario_c_text_plus_tool_call() -> tuple[MockChoice, str]:
    """
    Text + tool call in the same response.

    Hypothesis: logprobs.content contains tokens for BOTH the text portion
    AND the tool call argument tokens (all from the same forward pass).
    """
    text = "I'll search for that."
    args = '{"query": "Paris population"}'
    full_generated = text + args  # what vLLM actually generated before splitting
    tokens = _tokenise_string(full_generated)

    choice = MockChoice(
        message=MockMessage(
            content=text,
            tool_calls=[MockToolCall(id="call_002", type="function",
                                     function=MockFunction(name="search", arguments=args))],
        ),
        # If vLLM: all tokens present; if OpenAI standard: only text tokens
        logprobs=MockLogprobs(content=tokens),
        finish_reason="tool_calls",
    )
    return choice, "text + tool-call [vLLM hypothesis: all tokens present]"


def scenario_d_thinking_plus_tool_call() -> tuple[MockChoice, str]:
    """
    Extended thinking + tool call.
    ThinkingPart is parsed from <think>...</think> tags or reasoning_content.
    Logprobs cover the full generation stream.
    """
    thinking = "Let me think... the user wants to know about Paris."
    args = '{"query": "Paris population"}'
    full_generated = thinking + args
    tokens = _tokenise_string(full_generated)

    choice = MockChoice(
        message=MockMessage(
            content=None,
            tool_calls=[MockToolCall(id="call_003", type="function",
                                     function=MockFunction(name="search", arguments=args))],
        ),
        logprobs=MockLogprobs(content=tokens),
        finish_reason="tool_calls",
    )
    # Note: ThinkingPart would come from reasoning_content attribute on message,
    # not from content. We're testing the logprob token coverage here.
    return choice, "thinking + tool-call"


# ---------------------------------------------------------------------------
# Core algorithm: split a flat logprob list across parts using token strings
# ---------------------------------------------------------------------------


def reconstruct_full_text(tokens: list[MockTokenLogprob]) -> str:
    """Join token strings to reconstruct the full generated text."""
    return "".join(t.token for t in tokens)


def find_token_boundary(tokens: list[MockTokenLogprob], char_offset: int) -> int:
    """
    Find the token index where the cumulative character position reaches char_offset.
    Returns the index of the first token that starts AT or AFTER char_offset.
    """
    pos = 0
    for i, tok in enumerate(tokens):
        if pos >= char_offset:
            return i
        pos += len(tok.token)
    return len(tokens)


def split_logprobs_by_parts(
    tokens: list[MockTokenLogprob],
    text_content: str | None,
    tool_call_args: str | None,
) -> dict[str, list[MockTokenLogprob]]:
    """
    Split a flat logprob list across TextPart and ToolCallPart boundaries.

    Strategy:
      1. Reconstruct the full generated string by joining token.token strings.
      2. If text_content is present, it starts at position 0 — find the
         token boundary at len(text_content).
      3. Everything after that belongs to the tool call.

    Correctness assumption: the full generated string == text_content + tool_call_args
    (possibly with a separator). If this doesn't hold, boundary detection fails.

    Returns a dict with keys "text" and "tool_call" (either may be None/empty).
    """
    if not tokens:
        return {"text": [], "tool_call": []}

    full = reconstruct_full_text(tokens)
    result: dict[str, list[MockTokenLogprob]] = {"text": [], "tool_call": []}

    print(f"  Full reconstructed text ({len(full)} chars): {full!r}")

    if text_content and tool_call_args:
        # Verify our assumption: full text should start with text_content
        if full.startswith(text_content):
            split_at = find_token_boundary(tokens, len(text_content))
            result["text"] = tokens[:split_at]
            result["tool_call"] = tokens[split_at:]
            print(f"  Boundary found at token index {split_at}")
            print(f"  Text tokens:      {len(result['text'])} "
                  f"covering {sum(len(t.token) for t in result['text'])} chars")
            print(f"  Tool call tokens: {len(result['tool_call'])} "
                  f"covering {sum(len(t.token) for t in result['tool_call'])} chars")
            # Verify coverage
            expected_tool_chars = len(tool_call_args)
            actual_tool_chars = sum(len(t.token) for t in result["tool_call"])
            if actual_tool_chars == expected_tool_chars:
                print(f"  ✓ Tool call token coverage exact ({actual_tool_chars} chars)")
            else:
                print(f"  ✗ Coverage mismatch: expected {expected_tool_chars} chars, "
                      f"got {actual_tool_chars}")
        else:
            print(f"  ✗ Cannot split: full text does not start with text_content")
            print(f"    Expected prefix: {text_content!r}")
            print(f"    Actual start:    {full[:len(text_content)]!r}")
            result["text"] = tokens  # fall back: all tokens to text
    elif text_content:
        result["text"] = tokens
    elif tool_call_args:
        result["tool_call"] = tokens

    return result


# ---------------------------------------------------------------------------
# Simulate what PydanticAI does: extract provider_details from a mock choice
# ---------------------------------------------------------------------------


def extract_provider_details(choice: MockChoice) -> dict[str, Any] | None:
    """Mirrors the PydanticAI OpenAI model parsing logic (openai.py lines 412-427)."""
    if choice.logprobs is not None and choice.logprobs.content:
        return {
            "logprobs": [
                {
                    "token": lp.token,
                    "logprob": lp.logprob,
                    "top_logprobs": [],
                }
                for lp in choice.logprobs.content
            ]
        }
    return None


def extract_parts(choice: MockChoice) -> list[dict[str, Any]]:
    """Mirrors PydanticAI part extraction (openai.py lines 429-442)."""
    parts = []
    if choice.message.content is not None:
        parts.append({"part_kind": "text", "content": choice.message.content})
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            parts.append({
                "part_kind": "tool-call",
                "tool_name": tc.function.name,
                "args": tc.function.arguments,
                "tool_call_id": tc.id,
            })
    return parts


# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------


def run_scenario(label: str, choice: MockChoice) -> None:
    print(f"\n{'=' * 70}")
    print(f"SCENARIO: {label}")
    print(f"{'=' * 70}")

    parts = extract_parts(choice)
    provider_details = extract_provider_details(choice)

    text_content = next((p["content"] for p in parts if p["part_kind"] == "text"), None)
    tool_call_args = next((p["args"] for p in parts if p["part_kind"] == "tool-call"), None)

    print(f"\nParts extracted by PydanticAI:")
    for p in parts:
        print(f"  {p['part_kind']}: {str(p)[:80]}")

    print(f"\nprovider_details: {'present' if provider_details else 'None'}")
    if provider_details:
        lps = provider_details["logprobs"]
        full_text = "".join(lp["token"] for lp in lps)
        print(f"  logprob entries: {len(lps)}")
        print(f"  reconstructed:   {full_text!r}")
        print(f"  total chars:     {len(full_text)}")

        if text_content:
            print(f"\nText content ({len(text_content)} chars): {text_content!r}")
        if tool_call_args:
            print(f"Tool call args ({len(tool_call_args)} chars): {tool_call_args!r}")

        if text_content or tool_call_args:
            print(f"\nSplitting attempt:")
            tokens = choice.logprobs.content  # type: ignore[union-attr]
            split_logprobs_by_parts(tokens, text_content, tool_call_args)
    else:
        print("  → No logprobs captured. Tool call tokens NOT in logprobs.content.")
        print("  → This is the standard OpenAI behaviour.")
        print("  → If vLLM also behaves this way, logprobs for tool call args are unavailable.")


def main() -> None:
    print("=" * 70)
    print("SPIKE: vLLM logprob splitting across ModelResponse parts")
    print("=" * 70)
    print("""
WHAT WE'RE TESTING
------------------
PydanticAI reads logprobs from choice.logprobs.content (text tokens only,
per OpenAI API spec). The question: does vLLM put tool call argument tokens
in logprobs.content too?

This script tests the splitting algorithm using mocks. The [LIVE] section
(requires VLLM_BASE_URL env var) answers the empirical question definitively.
""")

    # Scenario A: text only
    choice_a, label_a = scenario_a_text_only()
    run_scenario(label_a, choice_a)

    # Scenario B: tool call only — two sub-cases
    b1, label_b1, b2, label_b2 = scenario_b_tool_call_only()  # type: ignore[misc]
    run_scenario(label_b1, b1)
    run_scenario(label_b2, b2)

    # Scenario C: text + tool call
    choice_c, label_c = scenario_c_text_plus_tool_call()
    run_scenario(label_c, choice_c)

    # Scenario D: thinking + tool call
    choice_d, label_d = scenario_d_thinking_plus_tool_call()
    run_scenario(label_d, choice_d)

    # ---------------------------------------------------------------------------
    # LIVE verification
    # ---------------------------------------------------------------------------
    vllm_url = os.environ.get("VLLM_BASE_URL")
    if not vllm_url:
        print(f"\n{'=' * 70}")
        print("LIVE VERIFICATION (skipped — set VLLM_BASE_URL to run)")
        print(f"{'=' * 70}")
        print("""
To verify against a real vLLM instance:

    VLLM_BASE_URL=http://localhost:8000 uv run python scripts/spike_logprob_splitting.py

The live path will:
  1. Make a real vLLM call with a tool-use prompt and logprobs=True
  2. Print the raw choice.logprobs.content to show whether tool call tokens appear
  3. Run the splitting algorithm on the real response

KEY QUESTION: when finish_reason == "tool_calls" and message.content is None,
does choice.logprobs.content contain the tool call argument tokens?
  - YES → splitting is possible; token strings give us the boundary
  - NO  → tool call argument logprobs are unavailable via PydanticAI today
""")
        return

    print(f"\n{'=' * 70}")
    print(f"LIVE VERIFICATION against {vllm_url}")
    print(f"{'=' * 70}")

    try:
        import asyncio

        from openai import AsyncOpenAI

        async def live_check() -> None:
            client = AsyncOpenAI(base_url=vllm_url, api_key="dummy")

            # List available models
            models = await client.models.list()
            model_id = models.data[0].id
            print(f"Using model: {model_id}")

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "search",
                        "description": "Search the web",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    },
                }
            ]

            print("\n--- Probe 1: tool-call-only (no text content) ---")
            resp = await client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Search for Paris population. Use the search tool."}],
                tools=tools,
                tool_choice="required",
                logprobs=True,
                top_logprobs=1,
                max_tokens=64,
            )
            choice = resp.choices[0]
            print(f"finish_reason:          {choice.finish_reason}")
            print(f"message.content:        {choice.message.content!r}")
            print(f"tool_calls present:     {choice.message.tool_calls is not None}")
            if choice.message.tool_calls:
                tc = choice.message.tool_calls[0]
                print(f"tool call args:         {tc.function.arguments!r}")
            print(f"logprobs.content:       {choice.logprobs}")

            if choice.logprobs and choice.logprobs.content:
                tokens = choice.logprobs.content
                full = "".join(t.token for t in tokens)
                print(f"\n✓ logprobs.content HAS {len(tokens)} entries")
                print(f"  Reconstructed: {full!r}")
                if choice.message.tool_calls:
                    args = choice.message.tool_calls[0].function.arguments
                    if args in full:
                        print(f"  ✓ Tool call args FOUND in reconstructed logprob text")
                        print(f"    → vLLM DOES include tool call tokens in logprobs.content")
                        print(f"    → Splitting is possible via token string matching")
                    else:
                        print(f"  ~ Args not verbatim in logprob text (format difference?)")
                        print(f"    Args:         {args!r}")
                        print(f"    Logprob text: {full!r}")
            else:
                print(f"\n✗ logprobs.content is empty/None for tool-call-only response")
                print(f"  → vLLM follows standard OpenAI behaviour")
                print(f"  → Tool call argument logprobs are NOT available via this API path")

            print("\n--- Probe 2: text + tool call ---")
            resp2 = await client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Tell me briefly what you're about to search for, then search for Paris population."}],
                tools=tools,
                logprobs=True,
                top_logprobs=1,
                max_tokens=128,
            )
            choice2 = resp2.choices[0]
            print(f"finish_reason:   {choice2.finish_reason}")
            print(f"message.content: {choice2.message.content!r}")
            if choice2.logprobs and choice2.logprobs.content:
                full2 = "".join(t.token for t in choice2.logprobs.content)
                print(f"logprob tokens:  {len(choice2.logprobs.content)} — reconstructed: {full2!r}")
                if choice2.message.tool_calls:
                    args2 = choice2.message.tool_calls[0].function.arguments
                    text2 = choice2.message.content or ""
                    expected_len = len(text2) + len(args2)
                    print(f"text chars: {len(text2)}, tool args chars: {len(args2)}, "
                          f"total expected: {expected_len}, logprob chars: {len(full2)}")
                    if len(full2) >= expected_len:
                        print("✓ logprob coverage includes both text AND tool call tokens")
                    elif len(full2) == len(text2):
                        print("~ logprob coverage matches text only (tool call tokens absent)")
                    else:
                        print(f"? Unexpected coverage ({len(full2)} chars)")

        asyncio.run(live_check())

    except ImportError:
        print("openai package not available in this env — skipping live check")
    except Exception as e:
        print(f"Live check failed: {e}")


if __name__ == "__main__":
    main()
