"""MiniF2F stakeholder that provides proof hints from ground truth."""

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from h_arcane.benchmarks.common import format_conversation_history
from h_arcane.core._internal.agents.base import BaseStakeholder
from h_arcane.core._internal.communication.schemas import MessageResponse
from h_arcane.core.settings import settings


class MiniF2FStakeholder(BaseStakeholder):
    """Provides proof hints from ground truth without revealing the full proof."""

    HINT_PROMPT = """You have access to a ground truth proof for this Lean 3 Mathlib theorem.
When asked about proof strategy, provide helpful hints WITHOUT revealing the full proof.

IMPORTANT: This is Lean 3 with Mathlib. Always use correct import paths:
- Use `.basic` suffix: `import data.real.basic`, `import data.finset.basic`
- `import tactic` gives most tactics
- `import algebra.big_operators.basic` for ∑ and ∏ notation (with `open_locale big_operators`)

Hints should guide toward:
- Correct Lean 3 Mathlib imports (with .basic suffix)
- Proof strategies (induction, cases, contradiction, etc.)
- Useful tactics (simp, ring, linarith, norm_num, field_simp, norm_cast, etc.)
- Key lemmas or facts that might help
- General approach without giving away the solution

Be encouraging and helpful, but don't reveal the complete proof."""

    def __init__(
        self,
        ground_truth_proof: str,
        problem_statement: str,
        model: str = "gpt-4o",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        seed: int | None = None,
    ):
        """
        Initialize stakeholder with ground truth proof.

        Args:
            ground_truth_proof: The complete ground truth proof (for generating hints)
            problem_statement: The theorem statement to prove
            model: LLM model to use for answering
            max_tokens: Maximum tokens for response
            temperature: Temperature for LLM
            seed: Random seed for deterministic responses
        """
        self.ground_truth_proof = ground_truth_proof
        self.problem_statement = problem_statement
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._seed = seed
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def model(self) -> str:
        """LLM model used by this stakeholder."""
        return self._model

    @property
    def system_prompt(self) -> str:
        """System prompt describing stakeholder behavior (for logging)."""
        return self.HINT_PROMPT

    async def answer(
        self,
        question: str,
        history: list[MessageResponse] | None = None,
    ) -> str:
        """
        Answer a question with a helpful hint based on ground truth proof.

        Args:
            question: The worker's question about proof strategy
            history: Previous Q&A pairs in this thread (oldest first)

        Returns:
            Hint string that guides without revealing the full proof

        Example:
            ```python
            stakeholder = MiniF2FStakeholder(ground_truth_proof, problem_statement)
            hint = await stakeholder.answer("What strategy should I use?")
            # Returns: "Consider using induction on n..."
            ```
        """
        history_text = format_conversation_history(history)
        history_section = f"\n\nPrevious conversation:\n{history_text}" if history_text else ""

        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=self.HINT_PROMPT,
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=f"""Problem statement:
{self.problem_statement}

Ground truth proof (for reference only - don't reveal this):
{self.ground_truth_proof}
{history_section}

Question: {question}

Provide a helpful hint without revealing the complete proof.""",
            ),
        ]

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            seed=self._seed,
        )

        content = response.choices[0].message.content
        if content is None:
            return "I'm unable to provide a hint at this time."
        return content
