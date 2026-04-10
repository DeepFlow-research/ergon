"""GDPEval toolkit — tool wrappers for document-processing workers.

Each public method returns a ``pydantic_ai.tools.Tool`` that delegates
to the sandbox manager for actual execution.  The toolkit also owns the
stakeholder Q&A channel.
"""

from typing import TYPE_CHECKING, Any
from uuid import UUID

try:
    from pydantic_ai.tools import Tool
except ImportError:
    Tool = None  # type: ignore[assignment,misc]

from ergon_builtins.benchmarks.gdpeval.task_schemas import (
    CreateCsvResponse,
    CreateDocxResponse,
    CreateExcelResponse,
    OcrImageResponse,
    ReadCsvResponse,
    ReadExcelResponse,
    ReadPDFResponse,
    RunPythonResponse,
)

if TYPE_CHECKING:
    from ergon_core.core.providers.sandbox.manager import BaseSandboxManager


class QAExchange:
    """Record of one worker ↔ stakeholder exchange."""

    __slots__ = ("question", "answer")

    def __init__(self, question: str, answer: str) -> None:
        self.question = question
        self.answer = answer


class GDPEvalToolkit:
    """Tool surface for GDPEval document-processing workers.

    Provides tools for reading/writing documents, running Python,
    performing OCR, and asking a stakeholder clarifying questions.
    """

    def __init__(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        sandbox_manager: "BaseSandboxManager",
        stakeholder: Any | None = None,  # slopcop: ignore[no-typing-any]
        max_questions: int = 10,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.sandbox_manager = sandbox_manager
        self.stakeholder = stakeholder
        self.max_questions = max_questions
        self._questions_asked = 0
        self._qa_history: list[QAExchange] = []

    @property
    def questions_asked(self) -> int:
        return self._questions_asked

    def get_qa_history(self) -> list[QAExchange]:
        return list(self._qa_history)

    def get_tools(self) -> list[Tool]:
        """Return all GDP document-processing tools."""
        tools = [
            self._read_pdf(),
            self._read_csv(),
            self._read_excel(),
            self._create_docx(),
            self._create_excel(),
            self._create_csv(),
            self._ocr_image(),
            self._run_python(),
        ]
        if self.stakeholder is not None:
            tools.append(self._ask_stakeholder())
        return tools

    # -- stakeholder --------------------------------------------------------

    async def ask_stakeholder(self, question: str) -> str:
        if self.stakeholder is None:
            return "[No stakeholder configured for this task.]"
        if self._questions_asked >= self.max_questions:
            return f"[Maximum questions ({self.max_questions}) reached.]"

        answer = await self.stakeholder.answer(question)
        self._qa_history.append(QAExchange(question=question, answer=answer))
        self._questions_asked += 1
        return answer

    # -- tool factories -----------------------------------------------------

    def _read_pdf(self) -> Tool:
        async def read_pdf(file_path: str) -> ReadPDFResponse:
            """Extract text from a PDF file with page markers.

            Args:
                file_path: Path to the PDF (e.g. "/inputs/document.pdf")
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "read_pdf",
                ReadPDFResponse,
                file_path=file_path,
            )

        return Tool(function=read_pdf, takes_ctx=False)

    def _read_csv(self) -> Tool:
        async def read_csv(
            file_path: str,
            max_rows: int | None = None,
        ) -> ReadCsvResponse:
            """Read a CSV file and return its contents.

            Args:
                file_path: Path to the CSV file
                max_rows: Optional maximum rows to read
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "read_csv",
                ReadCsvResponse,
                file_path=file_path,
                max_rows=max_rows,
            )

        return Tool(function=read_csv, takes_ctx=False)

    def _read_excel(self) -> Tool:
        async def read_excel(
            file_path: str,
            sheet_name: str | None = None,
        ) -> ReadExcelResponse:
            """Read an Excel file and return data from the specified sheet.

            Args:
                file_path: Path to the Excel file
                sheet_name: Optional sheet name (defaults to first sheet)
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "read_excel",
                ReadExcelResponse,
                file_path=file_path,
                sheet_name=sheet_name,
            )

        return Tool(function=read_excel, takes_ctx=False)

    def _create_docx(self) -> Tool:
        async def create_docx(
            content: str,
            output_path: str,
            title: str | None = None,
            template_style: str = "normal",
        ) -> CreateDocxResponse:
            """Create a Word document with the given content.

            Args:
                content: Markdown content (supports # headings, paragraphs)
                output_path: Where to save — use /workspace/final_output/ for deliverables
                title: Optional document title
                template_style: Style template ("normal", "formal", "memo")
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "create_docx",
                CreateDocxResponse,
                content=content,
                output_path=output_path,
                title=title,
                template_style=template_style,
            )

        return Tool(function=create_docx, takes_ctx=False)

    def _create_excel(self) -> Tool:
        async def create_excel(
            data: list[list[str]],
            output_path: str,
            sheet_name: str = "Sheet1",
        ) -> CreateExcelResponse:
            """Create an Excel file with the given data.

            Args:
                data: 2-D list of cell values (rows × columns)
                output_path: Where to save — use /workspace/final_output/ for deliverables
                sheet_name: Name of the worksheet
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "create_excel",
                CreateExcelResponse,
                data=data,
                output_path=output_path,
                sheet_name=sheet_name,
            )

        return Tool(function=create_excel, takes_ctx=False)

    def _create_csv(self) -> Tool:
        async def create_csv(
            data: list[list[str]],
            output_path: str,
        ) -> CreateCsvResponse:
            """Create a CSV file with the given data.

            Args:
                data: 2-D list of cell values (rows × columns)
                output_path: Where to save — use /workspace/final_output/ for deliverables
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "create_csv",
                CreateCsvResponse,
                data=data,
                output_path=output_path,
            )

        return Tool(function=create_csv, takes_ctx=False)

    def _ocr_image(self) -> Tool:
        async def ocr_image(
            file_path: str,
            language: str = "eng",
        ) -> OcrImageResponse:
            """Extract text from an image using OCR.

            Args:
                file_path: Path to the image file (PNG, JPG, etc.)
                language: OCR language code (default: "eng")
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "ocr_image",
                OcrImageResponse,
                file_path=file_path,
                language=language,
            )

        return Tool(function=ocr_image, takes_ctx=False)

    def _run_python(self) -> Tool:
        async def execute_python_code(code: str) -> RunPythonResponse:
            """Execute Python code in the sandbox.

            Args:
                code: Python code to execute
            """
            return await self.sandbox_manager.run_skill(
                self.run_id,
                "run_python",
                RunPythonResponse,
                code=code,
            )

        return Tool(function=execute_python_code, takes_ctx=False)

    def _ask_stakeholder(self) -> Tool:
        async def ask_stakeholder(question: str) -> str:
            """Ask the stakeholder a clarifying question.

            Args:
                question: Your question for the stakeholder
            """
            return await self.ask_stakeholder(question)

        return Tool(function=ask_stakeholder, takes_ctx=False)
