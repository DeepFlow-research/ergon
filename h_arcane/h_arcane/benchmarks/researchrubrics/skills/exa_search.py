"""Exa web search skill - searches the web and returns ranked results with content."""

from .exa_client import get_exa_client
from .responses import ExaSearchResponse, ExaSearchResult


async def main(
    query: str,
    num_results: int = 5,
    category: str | None = None,
) -> ExaSearchResponse:
    """
    Search the web using Exa to get ranked search results with content.

    Args:
        query: Search query string
        num_results: Number of results to return (default: 5, max recommended: 10)
        category: Optional content category filter (e.g., "news", "academic", "company")

    Returns:
        ExaSearchResponse with search results including titles, URLs, summaries, and content
    """
    try:
        if not query or not query.strip():
            return ExaSearchResponse(
                success=False,
                error="Query cannot be empty",
            )

        # Use search_and_contents to get both metadata and text content
        client = get_exa_client()
        response = client.search_and_contents(
            query,
            type="auto",  # Auto-detect best search type
            text=True,  # Include text content
            num_results=num_results,
            summary=True,  # Include summaries
            category=category if category else None,
        )

        results = [
            ExaSearchResult(
                title=result.title or "Untitled",
                url=result.url,
                summary=result.summary,
                # Truncate content to avoid huge responses (first 5000 chars)
                content=result.text[:5000] if result.text else None,
                published_date=result.published_date,
            )
            for result in response.results
        ]

        return ExaSearchResponse(
            success=True,
            query=query,
            results=results,
        )

    except Exception as e:
        return ExaSearchResponse(
            success=False,
            error=f"Error searching with Exa: {str(e)}",
        )
