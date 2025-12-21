"""OCR Image skill - extracts text from images using OCR."""

import pytesseract
from PIL import Image
from pathlib import Path

from .responses import OcrImageResponse


async def main(file_path: str, language: str = "eng") -> OcrImageResponse:
    """
    Extract text from image using OCR.

    Args:
        file_path: Path to image file (e.g., "/inputs/screenshot.png")
        language: OCR language code (default: "eng")

    Returns:
        OcrImageResponse with extracted text
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return OcrImageResponse(
                success=False, 
                error=f"Image file not found at {file_path}"
            )

        image = Image.open(file_path)
        text = pytesseract.image_to_string(image, lang=language)

        if not text.strip():
            return OcrImageResponse(
                success=False, 
                error="No text could be extracted from the image"
            )

        return OcrImageResponse(success=True, text=text.strip())

    except Exception as e:
        return OcrImageResponse(success=False, error=f"Error performing OCR: {str(e)}")

