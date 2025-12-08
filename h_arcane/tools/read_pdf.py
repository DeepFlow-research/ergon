"""Read PDF tool - works in sandbox or locally."""

import pdfplumber
from pathlib import Path

from responses import ReadPDFResponse


async def read_pdf(file_path: str) -> ReadPDFResponse:
    """
    Extract text from PDF file with page markers.

    Args:
        file_path: Path to PDF file (e.g., "/inputs/document.pdf" or "/workspace/report.pdf")

    Returns:
        ReadPDFResponse with extracted text or error message

    Example:
        ```python
        result = await read_pdf("/inputs/report.pdf")
        if result.success:
            print(result.text)  # "--- Page 1 ---\nContent..."
        else:
            print(result.error)
        ```
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return ReadPDFResponse(
                success=False, error=f"PDF file not found at {file_path}", text=None
            )

        extracted_text = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    extracted_text.append(f"--- Page {page_num} ---\n{text}")

        if not extracted_text:
            return ReadPDFResponse(
                success=False, error="No text could be extracted from the PDF", text=None
            )

        return ReadPDFResponse(success=True, text="\n\n".join(extracted_text), error=None)
    except Exception as e:
        return ReadPDFResponse(success=False, error=f"Error reading PDF: {str(e)}", text=None)
