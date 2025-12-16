"""MiniF2F stakeholder that provides proof hints from ground truth."""

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from h_arcane.benchmarks.base import BaseStakeholder
from h_arcane.config.evaluation_config import evaluation_config
from h_arcane.settings import settings


class MiniF2FStakeholder(BaseStakeholder):
    """Provides proof hints from ground truth without revealing the full proof."""

    HINT_PROMPT = """You have access to a ground truth proof for this theorem.
When asked about proof strategy, provide helpful hints WITHOUT revealing the full proof.

Hints should guide toward:
- Proof strategies (induction, cases, contradiction, etc.)
- Useful tactics (simp, ring, linarith, etc.)
- Key lemmas or facts that might help
- General approach without giving away the solution

Be encouraging and helpful, but don't reveal the complete proof."""

    def __init__(
        self,
        ground_truth_proof: str,
        problem_statement: str,
        model: str | None = None,
    ):
        """
        Initialize stakeholder with ground truth proof.

        Args:
            ground_truth_proof: The complete ground truth proof (for generating hints)
            problem_statement: The theorem statement to prove
            model: LLM model to use for answering (None = use config default)
        """
        self.ground_truth_proof = ground_truth_proof
        self.problem_statement = problem_statement
        self.model = model or evaluation_config.llm_stakeholder.model
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def answer(self, question: str) -> str:
        """
        Answer a question with a helpful hint based on ground truth proof.

        Args:
            question: The worker's question about proof strategy

        Returns:
            Hint string that guides without revealing the full proof

        Example:
            ```python
            stakeholder = MiniF2FStakeholder(ground_truth_proof, problem_statement)
            hint = await stakeholder.answer("What strategy should I use?")
            # Returns: "Consider using induction on n..."
            ```
        """
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

Question: {question}

Provide a helpful hint without revealing the complete proof.""",
            ),
        ]

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=evaluation_config.llm_stakeholder.max_tokens,
            temperature=evaluation_config.llm_stakeholder.temperature,
            seed=evaluation_config.llm_stakeholder.seed,
        )

        content = response.choices[0].message.content
        if content is None:
            return "I'm unable to provide a hint at this time."
        return content
