"""Tool functions for agent - execute in sandbox."""

import json

from agents import function_tool

from h_arcane.agents.sandbox_executor import execute_in_sandbox, get_sandbox_manager


@function_tool
async def read_pdf(file_path: str) -> str:
    """
    Extract text content from a PDF file with page markers for easy navigation.

    This tool reads PDF files and extracts all text content, inserting page markers
    (e.g., "--- Page 1 ---") to help you identify which page text came from.

    Parameters:
        file_path (str):
            The absolute or relative path to the PDF file to read.
            Example: "/inputs/document.pdf" or "/workspace/report.pdf"

    Returns:
        str:
            The full text content of the PDF with page markers, or an error message if
            the file cannot be read or contains no extractable text.

    Example:
        ```python
        text = await read_pdf("/inputs/report.pdf")
        # Returns: "--- Page 1 ---\nContent...\n\n--- Page 2 ---\nMore content..."
        ```
    """
    result = await execute_in_sandbox("read_pdf", file_path=file_path)
    if result.get("success") and result.get("text"):
        return result["text"]
    else:
        error = result.get("error", "Failed to read PDF")
        return f"Error: {error}"


@function_tool
async def create_docx(
    content: str,
    output_path: str,
    title: str | None = None,
    template_style: str = "normal",
) -> str:
    """
    Create a Word document (DOCX) from markdown content.

    Parameters:
        content (str): Markdown-formatted content (supports # headings, paragraphs)
        output_path (str): Path where the DOCX file should be saved (use /workspace/ for outputs)
        title (str, optional): Document title
        template_style (str): Style template ("normal", "formal", "memo")

    Returns:
        str: Success message with file path and size, or error message

    Example:
        ```python
        result = await create_docx(
            content="# Title\n\nBody text",
            output_path="/workspace/report.docx",
            title="Report"
        )
        # Returns: "✅ Created DOCX: /workspace/report.docx (15234 bytes)"
        ```
    """
    result = await execute_in_sandbox(
        "create_docx",
        content=content,
        output_path=output_path,
        title=title,
        template_style=template_style,
    )
    if result.get("success") and result.get("output_path"):
        file_size = result.get("file_size", 0)
        return f"✅ Created DOCX: {result['output_path']} ({file_size} bytes)"
    else:
        error = result.get("error", "Failed to create DOCX")
        return f"Error: {error}"


@function_tool
async def read_excel(file_path: str, sheet_name: str | None = None) -> str:
    """
    Read and extract data from Microsoft Excel files (.xlsx, .xls).

    This tool reads Excel workbooks and extracts all data from a specified sheet or
    the active sheet. All cell values are preserved including formulas (calculated
    values), numbers, text, and dates.

    Parameters:
        file_path (str):
            The path to the Excel file to read.
            Example: "/inputs/spreadsheet.xlsx" or "/workspace/data.xlsx"
        sheet_name (str | None):
            Optional. The name of the specific sheet to read. If None, reads the
            active (first) sheet. Default: None.

    Returns:
        str:
            JSON string containing:
            - success: Whether the operation succeeded
            - sheet_name: Name of the sheet that was read
            - num_rows: Total number of rows
            - num_cols: Total number of columns
            - data: 2D array of cell values (rows and columns)

    Example:
        ```python
        result_json = await read_excel("/inputs/data.xlsx", sheet_name="Sheet1")
        # Returns JSON: {"success": true, "sheet_name": "Sheet1", "num_rows": 10, ...}
        ```
    """
    result = await execute_in_sandbox("read_excel", file_path=file_path, sheet_name=sheet_name)
    return json.dumps(result, indent=2)


@function_tool
async def create_excel(data: list[list], output_path: str, sheet_name: str = "Sheet1") -> str:
    """
    Create an Excel file from 2D array data.

    Parameters:
        data (list[list]): 2D array of data (list of rows, each row is list of cells)
        output_path (str): Path where the Excel file should be saved (use /workspace/ for outputs)
        sheet_name (str): Name of the sheet (default: "Sheet1")

    Returns:
        str: Success message with file path and size, or error message

    Example:
        ```python
        result = await create_excel(
            data=[["Name", "Age"], ["Alice", 30], ["Bob", 25]],
            output_path="/workspace/people.xlsx"
        )
        # Returns: "✅ Created Excel: /workspace/people.xlsx (8765 bytes)"
        ```
    """
    result = await execute_in_sandbox(
        "create_excel", data=data, output_path=output_path, sheet_name=sheet_name
    )
    if result.get("success") and result.get("output_path"):
        file_size = result.get("file_size", 0)
        return f"✅ Created Excel: {result['output_path']} ({file_size} bytes)"
    else:
        error = result.get("error", "Failed to create Excel")
        return f"Error: {error}"


@function_tool
async def read_csv(file_path: str, max_rows: int | None = None) -> str:
    """
    Read data from CSV file.

    Parameters:
        file_path (str): Path to CSV file (e.g., "/inputs/data.csv" or "/workspace/export.csv")
        max_rows (int | None): Optional maximum rows to read

    Returns:
        str: JSON string with success, data, num_rows, num_cols, or error

    Example:
        ```python
        result_json = await read_csv("/inputs/data.csv", max_rows=100)
        # Returns JSON: {"success": true, "num_rows": 100, "num_cols": 3, "data": [...]}
        ```
    """
    result = await execute_in_sandbox("read_csv", file_path=file_path, max_rows=max_rows)
    return json.dumps(result, indent=2)


@function_tool
async def create_csv(data: list[list], output_path: str) -> str:
    """
    Create CSV file from 2D array data.

    Parameters:
        data (list[list]): 2D array of data (list of rows, each row is list of cells)
        output_path (str): Path where the CSV file should be saved (use /workspace/ for outputs)

    Returns:
        str: Success message with file path and size, or error message

    Example:
        ```python
        result = await create_csv(
            data=[["Name", "Age"], ["Alice", "30"], ["Bob", "25"]],
            output_path="/workspace/people.csv"
        )
        # Returns: "✅ Created CSV: /workspace/people.csv (1234 bytes)"
        ```
    """
    result = await execute_in_sandbox("create_csv", data=data, output_path=output_path)
    if result.get("success") and result.get("output_path"):
        file_size = result.get("file_size", 0)
        return f"✅ Created CSV: {result['output_path']} ({file_size} bytes)"
    else:
        error = result.get("error", "Failed to create CSV")
        return f"Error: {error}"


@function_tool
async def execute_python_code(code: str, timeout_seconds: int = 30) -> str:
    """
    Execute Python code in a secure sandbox environment.

    This tool runs Python code in the sandbox with full package access.
    Files created in /workspace/ are automatically tracked as outputs.

    Parameters:
        code (str): Python code to execute
        timeout_seconds (int): Maximum execution time in seconds (default: 30)

    Returns:
        str: Execution results (stdout, stderr, exit_code)
    """
    # Note: execute_python_code uses the run's sandbox directly
    # We'll handle this specially in sandbox_executor
    sandbox_manager = get_sandbox_manager()
    if not sandbox_manager.sandbox:
        return "Error: Sandbox not available"

    execution = await sandbox_manager.sandbox.run_code(
        code, language="python", timeout=timeout_seconds
    )

    stdout_parts = []
    stderr_parts = []
    if execution.logs:
        for log in execution.logs.stdout:
            stdout_parts.append(log)
        for log in execution.logs.stderr:
            stderr_parts.append(log)

    result = {
        "stdout": "\n".join(stdout_parts),
        "stderr": "\n".join(stderr_parts),
        "exit_code": 0 if not execution.error else 1,
    }

    if execution.error:
        result["error"] = (
            str(execution.error.value)
            if hasattr(execution.error, "value")
            else str(execution.error)
        )

    return json.dumps(result, indent=2)


@function_tool
async def ocr_image(file_path: str, language: str = "eng") -> str:
    """
    Extract text from image using OCR.

    Parameters:
        file_path (str): Path to image file (e.g., "/inputs/screenshot.png" or "/workspace/image.jpg")
        language (str): OCR language code (default: "eng")

    Returns:
        str: Extracted text or error message

    Example:
        ```python
        text = await ocr_image("/inputs/screenshot.png", language="eng")
        # Returns: "Extracted text from image" or "Error: ..."
        ```
    """
    result = await execute_in_sandbox("ocr_image", file_path=file_path, language=language)
    if result.get("success") and result.get("text"):
        return result["text"]
    else:
        error = result.get("error", "Failed to perform OCR")
        return f"Error: {error}"
