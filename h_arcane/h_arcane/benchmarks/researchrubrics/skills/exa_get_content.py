"""Exa get content skill - extracts full content from a URL."""

from .exa_client import get_exa_client
from .responses import ExaGetContentResponse


async def main(url: str) -> ExaGetContentResponse:
    """
    Extract full content from a URL using Exa.

    Args:
        url: URL to extract content from

    Returns:
        ExaGetContentResponse with extracted content, title, and metadata
    """
    try:
        if not url or not url.strip():
            return ExaGetContentResponse(
                success=False,
                error="URL cannot be empty",
            )

        # Validate URL format (basic check)
        if not url.startswith(("http://", "https://")):
            return ExaGetContentResponse(
                success=False,
                error=f"Invalid URL format: {url}",
            )

        # Get contents for the URL
        client = get_exa_client()
        response = client.get_contents(
            [url],
            text=True,  # Include full text content
        )

        if not response.results:
            return ExaGetContentResponse(
                success=False,
                error=f"No content found for URL: {url}",
            )

        result = response.results[0]

        return ExaGetContentResponse(
            success=True,
            url=url,
            title=result.title,
            content=result.text,  # Full text content
            published_date=result.published_date,
        )

    except Exception as e:
        return ExaGetContentResponse(
            success=False,
            error=f"Error extracting content from URL: {str(e)}",
        )
