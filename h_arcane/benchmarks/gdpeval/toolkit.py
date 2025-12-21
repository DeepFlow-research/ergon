"""GDPEval toolkit - explicit tool wrappers for document processing skills."""

from uuid import UUID

from agents import function_tool, Tool

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.benchmarks.base import BaseToolkit, BaseStakeholder
from h_arcane.db.models import Message, MessageRole
from h_arcane.db.queries import queries

# Import response types from the skills package (same types used in VM!)
from h_arcane.skills.gdpeval.responses import (
    ReadPDFResponse,
    ReadCsvResponse,
    ReadExcelResponse,
    CreateDocxResponse,
    CreateExcelResponse,
    CreateCsvResponse,
    OcrImageResponse,
    RunPythonResponse,
)


class GDPEvalToolkit(BaseToolkit):
    """GDPEval benchmark toolkit with document processing tools."""

    def __init__(
        self,
        run_id: UUID,
        stakeholder: BaseStakeholder,
        sandbox_manager: SandboxManager,
        max_questions: int = 10,
    ):
        """
        Initialize GDPEval toolkit.

        Args:
            run_id: The run ID for logging messages and actions
            stakeholder: Stakeholder for answering questions
            sandbox_manager: SandboxManager for skill execution
            max_questions: Maximum number of questions allowed
        """
        self.run_id = run_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._questions_asked = 0
        self._message_num = 0

    @property
    def questions_asked(self) -> int:
        """Get number of questions asked so far."""
        return self._questions_asked

    def get_tools(self) -> list[Tool]:
        """Return all GDPEval tools."""
        return [
            self._read_pdf(),
            self._read_csv(),
            self._read_excel(),
            self._create_docx(),
            self._create_excel(),
            self._create_csv(),
            self._ocr_image(),
            self._run_python(),
            self._ask_stakeholder(),
        ]

    # ─────────────────────────────────────────────────────────────────
    # Explicit tool wrappers - each one is a thin shell around run_skill
    # ─────────────────────────────────────────────────────────────────

    def _read_pdf(self) -> Tool:
        @function_tool
        async def read_pdf(file_path: str) -> ReadPDFResponse:
            """
            Extract text from a PDF file with page markers.

            Args:
                file_path: Path to the PDF (e.g., "/inputs/document.pdf")

            Returns:
                Response model with extracted text and page count, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "read_pdf",
                ReadPDFResponse,
                file_path=file_path,
            )
            return result

        return read_pdf

    def _read_csv(self) -> Tool:
        @function_tool
        async def read_csv(file_path: str, max_rows: int | None = None) -> ReadCsvResponse:
            """
            Read a CSV file and return its contents.

            Args:
                file_path: Path to the CSV file
                max_rows: Optional maximum rows to read

            Returns:
                Response model with CSV data, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "read_csv",
                ReadCsvResponse,
                file_path=file_path,
                max_rows=max_rows,
            )
            return result

        return read_csv

    def _read_excel(self) -> Tool:
        @function_tool
        async def read_excel(file_path: str, sheet_name: str | None = None) -> ReadExcelResponse:
            """
            Read an Excel file and return data from specified sheet.

            Args:
                file_path: Path to the Excel file
                sheet_name: Optional sheet name (defaults to first sheet)

            Returns:
                Response model with sheet data, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "read_excel",
                ReadExcelResponse,
                file_path=file_path,
                sheet_name=sheet_name,
            )
            return result

        return read_excel

    def _create_docx(self) -> Tool:
        @function_tool
        async def create_docx(
            content: str,
            output_path: str,
            title: str | None = None,
            template_style: str = "normal",
        ) -> CreateDocxResponse:
            """
            Create a Word document with the given content.

            Args:
                content: Markdown content (supports # headings, paragraphs)
                output_path: Where to save (e.g., "/workspace/report.docx")
                title: Optional document title
                template_style: Style template ("normal", "formal", "memo")

            Returns:
                Response model with file path and size, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "create_docx",
                CreateDocxResponse,
                content=content,
                output_path=output_path,
                title=title,
                template_style=template_style,
            )
            return result

        return create_docx

    def _create_excel(self) -> Tool:
        @function_tool
        async def create_excel(
            data: list[list[str]],
            output_path: str,
            sheet_name: str = "Sheet1",
        ) -> CreateExcelResponse:
            """
            Create an Excel file with the given data.

            Args:
                data: 2D list of data (rows of cells)
                output_path: Where to save (e.g., "/workspace/data.xlsx")
                sheet_name: Name of the sheet

            Returns:
                Response model with file path and size, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "create_excel",
                CreateExcelResponse,
                data=data,
                output_path=output_path,
                sheet_name=sheet_name,
            )
            return result

        return create_excel

    def _create_csv(self) -> Tool:
        @function_tool
        async def create_csv(data: list[list[str]], output_path: str) -> CreateCsvResponse:
            """
            Create a CSV file with the given data.

            Args:
                data: 2D list of data (rows of cells)
                output_path: Where to save (e.g., "/workspace/data.csv")

            Returns:
                Response model with file path and size, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "create_csv",
                CreateCsvResponse,
                data=data,
                output_path=output_path,
            )
            return result

        return create_csv

    def _ocr_image(self) -> Tool:
        @function_tool
        async def ocr_image(file_path: str, language: str = "eng") -> OcrImageResponse:
            """
            Extract text from an image using OCR.

            Args:
                file_path: Path to image file (PNG, JPG, etc.)
                language: OCR language code (default: "eng")

            Returns:
                Response model with extracted text, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "ocr_image",
                OcrImageResponse,
                file_path=file_path,
                language=language,
            )
            return result

        return ocr_image

    def _run_python(self) -> Tool:
        @function_tool
        async def execute_python_code(code: str) -> RunPythonResponse:
            """
            Execute Python code in the sandbox.

            Args:
                code: Python code to execute

            Returns:
                Response model with stdout/stderr/return_value, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "run_python",
                RunPythonResponse,
                code=code,
            )
            return result

        return execute_python_code

    def _ask_stakeholder(self) -> Tool:
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """
            Ask the stakeholder a clarifying question.

            Args:
                question: Your question for the stakeholder

            Returns:
                The stakeholder's response.
            """
            if self._questions_asked >= self.max_questions:
                return f"[Maximum questions ({self.max_questions}) reached.]"

            # Log worker question
            queries.messages.create(
                Message(
                    run_id=self.run_id,
                    sender=MessageRole.WORKER,
                    content=question,
                    sequence_num=self._message_num,
                )
            )
            self._message_num += 1

            # Get answer
            answer = await self.stakeholder.answer(question)

            # Log stakeholder answer
            queries.messages.create(
                Message(
                    run_id=self.run_id,
                    sender=MessageRole.STAKEHOLDER,
                    content=answer,
                    sequence_num=self._message_num,
                )
            )
            self._message_num += 1

            self._questions_asked += 1
            return answer

        return ask_stakeholder
