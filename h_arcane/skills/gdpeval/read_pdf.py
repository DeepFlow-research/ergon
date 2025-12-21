"""Read PDF skill - extracts text from PDF files."""

import pdfplumber
from pathlib import Path

from .responses import ReadPDFResponse


async def main(file_path: str) -> ReadPDFResponse:
    """
    Extract text from PDF file with page markers.

    Args:
        file_path: Path to PDF file (e.g., "/inputs/document.pdf")

    Returns:
        ReadPDFResponse with extracted text and page count
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return ReadPDFResponse(
                success=False, 
                error=f"PDF file not found at {file_path}"
            )

        pages = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    pages.append(f"--- Page {page_num} ---\n{text}")

        if not pages:
            return ReadPDFResponse(
                success=False, 
                error="No text could be extracted from the PDF"
            )

        return ReadPDFResponse(
            success=True,
            text="\n\n".join(pages),
            page_count=len(pages),
        )

    except Exception as e:
        return ReadPDFResponse(success=False, error=f"Error reading PDF: {str(e)}")

