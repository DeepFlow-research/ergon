"""OCR tool for extracting text from images."""

import pytesseract
from PIL import Image
from pathlib import Path

from responses import OcrImageResponse


async def ocr_image(file_path: str, language: str = "eng") -> OcrImageResponse:
    """
    Extract text from image using OCR.

    Args:
        file_path: Path to image file (e.g., "/inputs/screenshot.png" or "/workspace/image.jpg")
        language: OCR language code (default: "eng")

    Returns:
        OcrImageResponse with extracted text or error message

    Example:
        ```python
        result = await ocr_image("/inputs/screenshot.png", language="eng")
        if result.success:
            print(result.text)  # Extracted text
        else:
            print(result.error)
        ```
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return OcrImageResponse(
                success=False, error=f"Image file not found at {file_path}", text=None
            )

        image = Image.open(file_path)
        text = pytesseract.image_to_string(image, lang=language)

        if not text.strip():
            return OcrImageResponse(
                success=False, error="No text could be extracted from the image", text=None
            )

        return OcrImageResponse(success=True, text=text.strip(), error=None)

    except Exception as e:
        return OcrImageResponse(success=False, error=f"Error performing OCR: {str(e)}", text=None)
