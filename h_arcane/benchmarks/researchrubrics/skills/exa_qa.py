"""Exa QA skill - gets direct answers to questions from web sources."""

from .exa_client import get_exa_client
from .responses import ExaQAResponse


async def main(question: str, num_results: int = 3) -> ExaQAResponse:
    """
    Get direct answers to questions using Exa's neural search capabilities.

    Uses Exa's "neural" search type optimized for question-answering.
    Returns the best answer from top sources.

    Args:
        question: Question to answer
        num_results: Number of sources to use for answering (default: 3)

    Returns:
        ExaQAResponse with answer and source citations
    """
    try:
        if not question or not question.strip():
            return ExaQAResponse(
                success=False,
                error="Question cannot be empty",
            )

        # Use neural search type optimized for Q&A
        client = get_exa_client()
        response = client.search_and_contents(
            question,
            type="neural",  # Neural search for better Q&A
            text=True,
            num_results=num_results,
            summary=True,  # Get summaries which often contain answers
        )

        if not response.results:
            return ExaQAResponse(
                success=True,
                question=question,
                answer="No answer found for this question.",
                sources=[],
            )

        # Use the summary from the top result as the answer
        # Summaries from neural search are often direct answers
        top_result = response.results[0]
        answer = (
            top_result.summary
            or (top_result.text[:500] if top_result.text else None)
            or "No answer found."
        )

        # Collect all sources for citation
        sources = [
            {"url": result.url, "title": result.title or "Untitled"} for result in response.results
        ]

        return ExaQAResponse(
            success=True,
            question=question,
            answer=answer,
            sources=sources,
        )

    except Exception as e:
        return ExaQAResponse(
            success=False,
            error=f"Error getting answer with Exa: {str(e)}",
        )
