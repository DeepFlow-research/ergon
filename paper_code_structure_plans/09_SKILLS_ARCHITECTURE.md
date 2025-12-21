# Skills Architecture: Benchmark-Scoped Tools

## Overview

Separate "core library" from "benchmark-specific tools". Each benchmark owns its complete toolset, making it self-contained and copyable to VMs.

## Goals

1. **Benchmark isolation**: GDPEval agents never see Lean tools, MiniF2F agents never see PDF tools
2. **Copy-to-VM friendly**: Each benchmark's tools folder can be copied as-is to `/skills` in VM
3. **Relative imports**: All benchmark tools use `from .responses import ...` so imports work identically local and in VM
4. **Single source of truth**: `ToolResponse` base class in core, benchmark responses extend it
5. **Simple execution**: `sandbox.run_skill(skill_path, **kwargs)` - no magic

---

## Directory Structure

```
h_arcane/
├── skills/                              # ← Skills that run IN the VM
│   │                                    # Each benchmark is a self-contained package
│   │
│   ├── gdpeval/                         # GDPEval benchmark tools
│   │   ├── __init__.py
│   │   ├── responses.py                 # GDPEval-specific response types
│   │   ├── read_pdf.py                  # main(file_path) -> dict
│   │   ├── read_csv.py
│   │   ├── read_excel.py
│   │   ├── create_docx.py
│   │   ├── create_excel.py
│   │   ├── create_csv.py
│   │   ├── ocr_image.py
│   │   └── run_python.py
│   │
│   ├── minif2f/                         # MiniF2F benchmark tools
│   │   ├── __init__.py
│   │   ├── responses.py                 # Lean-specific response types
│   │   ├── _utils.py                    # Lean installation, parsing helpers
│   │   ├── write_lean_file.py
│   │   ├── check_lean_file.py
│   │   └── verify_lean_proof.py
│   │
│   └── research_rubrics/                # Future: Research rubrics benchmark
│       ├── __init__.py
│       ├── responses.py
│       └── ...
│
├── benchmarks/                          # ← Benchmark configs (LOCAL, not in VM)
│   ├── base.py                          # BaseToolkit, BaseStakeholder protocols
│   ├── registry.py                      # Benchmark registry
│   │
│   ├── gdpeval/
│   │   ├── __init__.py
│   │   ├── config.py                    # GDPEVAL_WORKER_CONFIG
│   │   ├── toolkit.py                   # GDPEvalToolkit - defines which skills
│   │   ├── stakeholder.py
│   │   └── loader.py
│   │
│   └── minif2f/
│       ├── __init__.py
│       ├── config.py                    # MINIF2F_WORKER_CONFIG  
│       ├── toolkit.py                   # MiniF2FToolkit - defines which skills
│       ├── stakeholder.py
│       └── loader.py
│
├── agents/
│   ├── sandbox.py                       # SandboxManager with run_skill()
│   └── worker.py                        # ReActWorker
│
└── schemas/
    └── tools.py                         # ToolResult union type (for typing)
```

---

## Benchmark Skills

### Design Decision: Pydantic Models with Relative Imports

Skills use **Pydantic models** for responses with **relative imports** (`from .responses import ...`):

**Why Pydantic:**
- `.model_dump()` for clean JSON serialization
- `.model_validate()` for parsing with validation
- Full IDE support and type checking
- Consistent with rest of codebase
- E2B sandboxes have Pydantic pre-installed

**Why relative imports work in both contexts:**
- **VM**: `/skills/gdpeval/` is a package → `.responses` → `/skills/gdpeval/responses.py`
- **Local**: `h_arcane.skills.gdpeval` is a package → `.responses` → `h_arcane/skills/gdpeval/responses.py`

This gives us **typed responses everywhere** - including when the agent writes code that chains tools.

### `skills/gdpeval/responses.py` (Shared - works in VM and locally)

```python
"""Typed response models for GDPEval skills.

Uses Pydantic for validation and serialization. Works in VM and locally.
"""
from pydantic import BaseModel


class ReadPDFResponse(BaseModel):
    """Response from read_pdf skill."""
    success: bool
    text: str | None = None
    page_count: int | None = None
    error: str | None = None


class CreateDocxResponse(BaseModel):
    """Response from create_docx skill."""
    success: bool
    filename: str | None = None
    bytes_written: int | None = None
    error: str | None = None


class ReadExcelResponse(BaseModel):
    """Response from read_excel skill."""
    success: bool
    data: list[list] | None = None
    sheet_name: str | None = None
    row_count: int | None = None
    error: str | None = None


class CreateExcelResponse(BaseModel):
    """Response from create_excel skill."""
    success: bool
    filename: str | None = None
    bytes_written: int | None = None
    error: str | None = None


class OCRImageResponse(BaseModel):
    """Response from ocr_image skill."""
    success: bool
    text: str | None = None
    error: str | None = None
```

### Why This Enables Agent-Written Code

If the agent writes a script that chains tools:

```python
# Agent-written code running in VM
from gdpeval.read_pdf import main as read_pdf
from gdpeval.create_docx import main as create_docx
from gdpeval.responses import ReadPDFResponse, CreateDocxResponse  # Pydantic models!

async def process_and_summarize(pdf_path: str, output_path: str) -> dict:
    # Read PDF - response is a Pydantic model with full typing
    pdf_result: ReadPDFResponse = await read_pdf(file_path=pdf_path)
    
    if not pdf_result.success:
        return {"error": pdf_result.error}
    
    # Agent can access typed fields with IDE autocomplete
    summary = f"Document has {pdf_result.page_count} pages.\n\n{pdf_result.text[:500]}..."
    
    # Create output - response is typed
    docx_result: CreateDocxResponse = await create_docx(
        content=summary,
        output_path=output_path,
    )
    
    # Pydantic's .model_dump() for clean serialization
    return docx_result.model_dump()
```

The agent gets:
- IDE autocomplete (if using a code-aware model)
- Type hints for what fields exist
- Validation on construction
- Clean serialization with `.model_dump()`

### `skills/gdpeval/read_pdf.py`

```python
"""Read PDF skill."""
import pdfplumber
from pathlib import Path
from .responses import ReadPDFResponse  # Relative import - works in VM and locally!


async def main(file_path: str) -> ReadPDFResponse:
    """
    Extract text from PDF file with page markers.
    
    Args:
        file_path: Path to PDF (e.g., "/inputs/doc.pdf")
    
    Returns:
        ReadPDFResponse with text content and page count
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return ReadPDFResponse(
                success=False, 
                error=f"File not found: {file_path}"
            )
        
        pages = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                pages.append(f"--- Page {i} ---\n{text}")
        
        return ReadPDFResponse(
            success=True,
            text="\n\n".join(pages),
            page_count=len(pages),
        )
        
    except Exception as e:
        return ReadPDFResponse(success=False, error=str(e))
```

### `skills/minif2f/responses.py`

```python
"""Typed response models for MiniF2F Lean skills."""
from pydantic import BaseModel


class WriteLeanResponse(BaseModel):
    """Response from write_lean_file skill."""
    success: bool
    filename: str | None = None
    bytes_written: int | None = None
    error: str | None = None


class LeanCheckResponse(BaseModel):
    """Response from check_lean_file skill."""
    success: bool
    has_errors: bool = False
    errors: list[str] | None = None
    goals: list[str] | None = None
    warnings: list[str] | None = None
    error: str | None = None


class LeanVerificationResponse(BaseModel):
    """Response from verify_lean_proof skill."""
    success: bool
    verified: bool = False
    message: str | None = None
    proof_complete: bool = False
    error: str | None = None
```

### `skills/minif2f/write_lean_file.py`

```python
"""Write Lean file skill."""
from pathlib import Path
from .responses import WriteLeanResponse  # Relative import - works in VM and locally!


async def main(filename: str, content: str) -> WriteLeanResponse:
    """
    Write or update a Lean proof file.
    
    Args:
        filename: Name of file (e.g., "proof.lean")
        content: Lean code content
    
    Returns:
        WriteLeanResponse with filename and bytes written
    """
    try:
        filepath = Path("/workspace") / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        content_bytes = content.encode("utf-8")
        filepath.write_bytes(content_bytes)
        
        return WriteLeanResponse(
            success=True,
            filename=str(filepath),
            bytes_written=len(content_bytes),
        )
        
    except Exception as e:
        return WriteLeanResponse(success=False, error=str(e))
```

---

## Sandbox Interface

### `h_arcane/agents/sandbox.py`

```python
"""Sandbox management with skill execution."""
import json
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

# Generic type for skill responses (all inherit from BaseModel)
T = TypeVar("T", bound=BaseModel)


class SandboxManager:
    """Manages E2B sandboxes with benchmark-specific skills."""
    
    def __init__(self):
        self._sandboxes: dict[UUID, Sandbox] = {}
        self._skills_packages: dict[UUID, str] = {}  # run_id -> package name in VM
    
    async def create(
        self, 
        run_id: UUID, 
        skills_dir: Path,  # e.g., Path("h_arcane/skills/minif2f")
    ) -> "Sandbox":
        """
        Create sandbox and copy skills directory.
        
        Args:
            run_id: Unique run identifier
            skills_dir: Local path to skills folder to copy
        
        Example:
            skills_dir = Path(__file__).parent.parent / "skills" / "minif2f"
            sandbox = await manager.create(run_id, skills_dir)
        """
        sandbox = await Sandbox.create(...)
        
        # Copy the benchmark's skills package to /skills/{package_name}
        package_name = skills_dir.name  # e.g., "minif2f" or "gdpeval"
        await self._upload_directory(sandbox, skills_dir, f"/skills/{package_name}")
        
        self._sandboxes[run_id] = sandbox
        self._skills_packages[run_id] = package_name
        return sandbox
    
    async def _upload_directory(self, sandbox, local_dir: Path, remote_dir: str) -> None:
        """
        Upload a directory to the sandbox, preserving structure.
        
        IMPORTANT: Must include __init__.py files for Python package imports to work!
        """
        # Create remote directory
        await sandbox.commands.run(f"mkdir -p {remote_dir}")
        
        # Upload all .py files (including __init__.py!)
        for py_file in local_dir.rglob("*.py"):
            relative_path = py_file.relative_to(local_dir)
            remote_path = f"{remote_dir}/{relative_path}"
            
            # Ensure parent directories exist
            remote_parent = str(Path(remote_path).parent)
            await sandbox.commands.run(f"mkdir -p {remote_parent}")
            
            # Upload file
            content = py_file.read_bytes()
            await sandbox.files.write(remote_path, content)
    
    async def run_skill(
        self,
        run_id: UUID,
        skill_name: str,
        return_type: type[T],  # Generic return type for type safety
        **kwargs,
    ) -> T:
        """
        Run a skill in the sandbox with typed response.
        
        Args:
            run_id: Which sandbox
            skill_name: Name of skill (matches filename without .py)
            return_type: Dataclass type to parse the result into
            **kwargs: Arguments to skill's main()
        
        Returns:
            Parsed result of type T
        
        Example:
            result = await manager.run_skill(
                run_id,
                "read_pdf",
                ReadPDFResponse,  # <- Type hint AND runtime parser
                file_path="/inputs/doc.pdf"
            )
            # result is ReadPDFResponse, not dict
            if result.success:
                print(result.text)
        """
        sandbox = self._sandboxes[run_id]
        package = self._skills_packages[run_id]
        
        # Write kwargs to a temp file to avoid escaping issues
        kwargs_path = f"/tmp/kwargs_{skill_name}.json"
        await sandbox.files.write(kwargs_path, json.dumps(kwargs, default=str).encode())
        
        # Runner script:
        # - Reads kwargs from file
        # - Calls skill (returns Pydantic model)
        # - Serializes result via .model_dump()
        # - Writes to result file
        code = f'''
import json
import sys
sys.path.insert(0, '/skills')

from {package}.{skill_name} import main

with open("{kwargs_path}") as f:
    kwargs = json.load(f)

result = await main(**kwargs)

# Skill returns a Pydantic model - use .model_dump() for serialization
with open("/tmp/skill_result.json", "w") as f:
    json.dump(result.model_dump(), f, default=str)
'''
        
        execution = await sandbox.run_code(code, language="python")
        
        if execution.error:
            # Return error as the typed response
            return return_type(success=False, error=str(execution.error))
        
        # Read result from file and validate into typed response
        try:
            result_bytes = await sandbox.files.read("/tmp/skill_result.json")
            raw_result = json.loads(result_bytes.decode())
            # Pydantic validation
            return return_type.model_validate(raw_result)
        except Exception as e:
            stdout = "".join(execution.logs.stdout) if execution.logs else ""
            return return_type(success=False, error=f"Failed to read result: {e}. Stdout: {stdout[:200]}")
```

---

## Toolkit Pattern

Each toolkit defines **explicit thin wrapper functions** that call `run_skill()`. 
No metadata dicts - just real functions with real type hints.

### `h_arcane/benchmarks/gdpeval/toolkit.py`

```python
"""GDPEval toolkit - explicit tool wrappers for document processing skills."""
import json
from uuid import UUID

from agents import function_tool, Tool

from h_arcane.benchmarks.base import BaseToolkit
from h_arcane.agents.sandbox import SandboxManager
# Import response types from the skills package (same types used in VM!)
from h_arcane.skills.gdpeval.responses import (
    ReadPDFResponse,
    CreateDocxResponse,
    ReadExcelResponse,
)


class GDPEvalToolkit(BaseToolkit):
    """GDPEval benchmark toolkit with document processing tools."""
    
    def __init__(
        self,
        run_id: UUID,
        sandbox_manager: SandboxManager,
        stakeholder: "BaseStakeholder",
    ):
        self.run_id = run_id
        self.sandbox_manager = sandbox_manager
        self.stakeholder = stakeholder
        self._questions_asked = 0
    
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
        async def read_pdf(file_path: str) -> str:
            """
            Extract text from a PDF file with page markers.
            
            Args:
                file_path: Path to the PDF (e.g., "/inputs/document.pdf")
            
            Returns:
                Extracted text with page markers, or error message.
            """
            # Typed! result is ReadPDFResponse, not dict
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "read_pdf",
                ReadPDFResponse,  # <- Generic type parameter
                file_path=file_path,
            )
            if result.success:
                return result.text or ""
            return f"Error: {result.error}"
        
        return read_pdf
    
    def _read_csv(self) -> Tool:
        @function_tool
        async def read_csv(file_path: str) -> str:
            """
            Read a CSV file and return its contents.
            
            Args:
                file_path: Path to the CSV file
            
            Returns:
                CSV data as formatted string, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "read_csv", file_path=file_path
            )
            return json.dumps(result, indent=2)
        
        return read_csv
    
    def _read_excel(self) -> Tool:
        @function_tool
        async def read_excel(file_path: str, sheet_name: str | None = None) -> str:
            """
            Read an Excel file and return data from specified sheet.
            
            Args:
                file_path: Path to the Excel file
                sheet_name: Optional sheet name (defaults to first sheet)
            
            Returns:
                Sheet data as formatted string, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "read_excel", file_path=file_path, sheet_name=sheet_name
            )
            return json.dumps(result, indent=2)
        
        return read_excel
    
    def _create_docx(self) -> Tool:
        @function_tool
        async def create_docx(
            content: str,
            output_path: str,
            title: str | None = None,
        ) -> str:
            """
            Create a Word document with the given content.
            
            Args:
                content: Text content for the document
                output_path: Where to save (e.g., "/workspace/report.docx")
                title: Optional document title
            
            Returns:
                Success message with file path, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "create_docx",
                content=content, output_path=output_path, title=title
            )
            if result.get("success"):
                return f"Created: {result.get('filename')} ({result.get('bytes_written')} bytes)"
            return f"Error: {result.get('error')}"
        
        return create_docx
    
    def _create_excel(self) -> Tool:
        @function_tool
        async def create_excel(
            data: list[list],
            output_path: str,
            sheet_name: str = "Sheet1",
        ) -> str:
            """
            Create an Excel file with the given data.
            
            Args:
                data: 2D list of data (rows of cells)
                output_path: Where to save (e.g., "/workspace/data.xlsx")
                sheet_name: Name of the sheet
            
            Returns:
                Success message with file path, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "create_excel",
                data=data, output_path=output_path, sheet_name=sheet_name
            )
            return json.dumps(result, indent=2)
        
        return create_excel
    
    def _create_csv(self) -> Tool:
        @function_tool
        async def create_csv(data: list[list], output_path: str) -> str:
            """
            Create a CSV file with the given data.
            
            Args:
                data: 2D list of data (rows of cells)
                output_path: Where to save (e.g., "/workspace/data.csv")
            
            Returns:
                Success message with file path, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "create_csv", data=data, output_path=output_path
            )
            return json.dumps(result, indent=2)
        
        return create_csv
    
    def _ocr_image(self) -> Tool:
        @function_tool
        async def ocr_image(file_path: str) -> str:
            """
            Extract text from an image using OCR.
            
            Args:
                file_path: Path to image file (PNG, JPG, etc.)
            
            Returns:
                Extracted text, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "ocr_image", file_path=file_path
            )
            if result.get("success"):
                return result.get("text", "")
            return f"Error: {result.get('error')}"
        
        return ocr_image
    
    def _run_python(self) -> Tool:
        @function_tool
        async def run_python(code: str) -> str:
            """
            Execute Python code in the sandbox.
            
            Args:
                code: Python code to execute
            
            Returns:
                stdout/stderr from execution, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "run_python", code=code
            )
            return json.dumps(result, indent=2)
        
        return run_python
    
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
            self._questions_asked += 1
            response = await self.stakeholder.answer(question)
            return response
        
        return ask_stakeholder
    
    @property
    def questions_asked(self) -> int:
        return self._questions_asked
```

### `h_arcane/benchmarks/minif2f/toolkit.py`

```python
"""MiniF2F toolkit - explicit tool wrappers for Lean proof development."""
import json
from uuid import UUID

from agents import function_tool, Tool

from h_arcane.benchmarks.base import BaseToolkit
from h_arcane.agents.sandbox import SandboxManager
# Import response types from the skills package (same types used in VM!)
from h_arcane.skills.minif2f.responses import (
    WriteLeanResponse,
    LeanCheckResponse,
    LeanVerificationResponse,
)


class MiniF2FToolkit(BaseToolkit):
    """MiniF2F benchmark toolkit with Lean tools."""
    
    def __init__(
        self,
        run_id: UUID,
        sandbox_manager: SandboxManager,
        stakeholder: "BaseStakeholder",
    ):
        self.run_id = run_id
        self.sandbox_manager = sandbox_manager
        self.stakeholder = stakeholder
        self._questions_asked = 0
    
    def get_tools(self) -> list[Tool]:
        """Return all MiniF2F tools."""
        return [
            self._write_lean_file(),
            self._check_lean_file(),
            self._verify_lean_proof(),
            self._ask_stakeholder(),
        ]
    
    # ─────────────────────────────────────────────────────────────────
    # Lean-specific tool wrappers
    # ─────────────────────────────────────────────────────────────────
    
    def _write_lean_file(self) -> Tool:
        @function_tool
        async def write_lean_file(filename: str, content: str) -> str:
            """
            Write or update a Lean proof file.
            
            Use `sorry` as a placeholder for incomplete proofs - check_lean_file
            will show you the proof goals.
            
            Args:
                filename: Name of the file (e.g., "proof.lean")
                content: Complete Lean file content
            
            Returns:
                Success message with bytes written, or error message.
            """
            # Typed! result is WriteLeanResponse
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "write_lean_file",
                WriteLeanResponse,
                filename=filename,
                content=content,
            )
            if result.success:
                return f"Wrote {result.bytes_written} bytes to {result.filename}"
            return f"Error: {result.error}"
        
        return write_lean_file
    
    def _check_lean_file(self) -> Tool:
        @function_tool
        async def check_lean_file(filename: str) -> str:
            """
            Check a Lean file for errors and get proof goals.
            
            Use this after write_lean_file to see:
            - Syntax/type errors
            - Unsolved goals (what you need to prove)
            - Warnings
            
            Args:
                filename: Name of the Lean file to check
            
            Returns:
                Check results with errors, goals, and warnings.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "check_lean_file", filename=filename
            )
            return json.dumps(result, indent=2)
        
        return check_lean_file
    
    def _verify_lean_proof(self) -> Tool:
        @function_tool
        async def verify_lean_proof(filename: str) -> str:
            """
            Verify a complete Lean proof (no `sorry` allowed).
            
            Call this when you believe your proof is complete.
            The proof must compile without errors and contain no `sorry`.
            
            Args:
                filename: Name of the Lean file to verify
            
            Returns:
                Verification result - success or failure with details.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id, "verify_lean_proof", filename=filename
            )
            if result.get("verified"):
                return "✓ Proof verified successfully!"
            return f"✗ Verification failed: {result.get('message', 'Unknown error')}"
        
        return verify_lean_proof
    
    def _ask_stakeholder(self) -> Tool:
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """
            Ask for a hint about the proof strategy.
            
            Args:
                question: Your question about the proof
            
            Returns:
                A hint or guidance from the stakeholder.
            """
            self._questions_asked += 1
            response = await self.stakeholder.answer(question)
            return response
        
        return ask_stakeholder
    
    @property
    def questions_asked(self) -> int:
        return self._questions_asked
```

---

## VM State After Setup

When a sandbox is created with `skills_dir=Path("h_arcane/skills/gdpeval")`:

```
/skills/
└── gdpeval/                 # Package name derived from skills_dir.name
    ├── __init__.py
    ├── responses.py         # Dataclass helpers for building result dicts
    ├── read_pdf.py          # async def main(...) -> dict
    ├── create_docx.py
    └── ...

/inputs/                     # Task input files
/workspace/                  # Working directory
```

When a sandbox is created with `skills_dir=Path("h_arcane/skills/minif2f")`:

```
/skills/
└── minif2f/
    ├── __init__.py
    ├── responses.py         # Dataclass helpers for building result dicts
    ├── _utils.py            # Lean helpers (install, parse output)
    ├── write_lean_file.py   # async def main(...) -> dict
    ├── check_lean_file.py
    └── verify_lean_proof.py

/inputs/
/workspace/
```

---

## Execution Flow

```
1. Experiment starts for benchmark=minif2f
   │
2. worker_execute handler determines skills_dir:
   │     skills_dir = Path(__file__).parent.parent / "skills" / "minif2f"
   │
3. SandboxManager.create(run_id, skills_dir)
   │  └─ Copies skills_dir to /skills/minif2f in VM
   │
4. MiniF2FToolkit created with sandbox_manager reference
   │
5. toolkit.get_tools() returns explicit @function_tool wrappers
   │  └─ Each wrapper calls sandbox_manager.run_skill(...)
   │
6. Agent calls write_lean_file(filename="proof.lean", content="...")
   │
7. Wrapper function executes:
   │     result = await self.sandbox_manager.run_skill(
   │         self.run_id, "write_lean_file", filename="...", content="..."
   │     )
   │
8. SandboxManager.run_skill():
   │  a. Writes kwargs to /tmp/kwargs_write_lean_file.json
   │  b. Executes: from minif2f.write_lean_file import main; result = await main(**kwargs)
   │  c. Reads result from /tmp/skill_result.json
   │
9. Result returned to agent as formatted string
```

---

## Adding a New Benchmark

1. **Create skills folder**: `h_arcane/skills/new_benchmark/`
   ```
   skills/new_benchmark/
   ├── __init__.py
   ├── responses.py        # Your response dataclasses
   ├── skill_one.py        # async def main(...) -> dict
   └── skill_two.py        # async def main(...) -> dict
   ```

2. **Create benchmark config**: `h_arcane/benchmarks/new_benchmark/`
   ```python
   # toolkit.py
   class NewBenchmarkToolkit(BaseToolkit):
       def get_tools(self) -> list[Tool]:
           return [
               self._skill_one(),
               self._skill_two(),
               self._ask_stakeholder(),
           ]
       
       def _skill_one(self) -> Tool:
           @function_tool
           async def skill_one(arg1: str, arg2: int) -> str:
               """Description of skill one."""
               result = await self.sandbox_manager.run_skill(
                   self.run_id, "skill_one", arg1=arg1, arg2=arg2
               )
               return json.dumps(result, indent=2)
           return skill_one
       
       # ... etc
   ```

3. **Register in registry**: `h_arcane/benchmarks/registry.py`
   ```python
   BENCHMARKS = {
       BenchmarkName.NEW_BENCHMARK: {
           "config": NEW_BENCHMARK_CONFIG,
           "toolkit_class": NewBenchmarkToolkit,
           "skills_dir": Path(__file__).parent.parent / "skills" / "new_benchmark",
           "loader": load_new_benchmark_to_database,
       },
   }
   ```

4. **Use in worker_execute**:
   ```python
   benchmark_config = BENCHMARKS[benchmark_name]
   skills_dir = benchmark_config["skills_dir"]
   await sandbox_manager.create(run_id, skills_dir)
   ```

---

## Benefits

1. **Complete isolation**: GDPEval VM has no Lean code, MiniF2F VM has no PDF code
2. **Simple mental model**: Skills folder → copied to VM → executed via `run_skill()`
3. **Relative imports work**: `from .responses import X` works in both contexts
4. **Easy to test**: Can run skill files directly in test environment
5. **No import path confusion**: VM always imports from `/skills/{benchmark}/`
6. **Type safety**: `ToolResult` union type for local type checking
7. **Benchmark-scoped**: Each benchmark is fully self-contained

---

## Migration Path

1. Create `h_arcane/skills/` directory structure
2. Move `h_arcane/tools/*.py` → `h_arcane/skills/gdpeval/`
3. Move `h_arcane/tools/formal_math/*.py` → `h_arcane/skills/minif2f/`
4. Create `responses.py` in each skills folder with Pydantic response models
5. Refactor each skill:
   - Use relative imports: `from .responses import XResponse`
   - Return Pydantic model: `async def main(...) -> XResponse`
6. Update `SandboxManager.create()` to accept `skills_dir: Path`
7. Add generic `run_skill[T]()` method with typed return using `model_validate()`
8. Rewrite toolkits:
   - Import response types from skills package
   - Explicit `@function_tool` wrapper methods
9. Update `worker_execute` to pass `skills_dir` when creating sandbox
10. Delete old `h_arcane/tools/` directory

---

---

## Import Path Analysis

### Why Relative Imports Work in VM

When we execute:
```python
sys.path.insert(0, '/skills')
from gdpeval.read_pdf import main
```

Python's import sequence:
1. Looks for `gdpeval` in `/skills/` → finds `/skills/gdpeval/`
2. Checks for `__init__.py` → **MUST exist** for package recognition
3. Imports `read_pdf.py` as module `gdpeval.read_pdf`
4. Sets `read_pdf.__package__ = "gdpeval"`
5. When `read_pdf.py` does `from .responses import ReadPDFResponse`:
   - Python resolves `.responses` relative to `__package__`
   - Imports `/skills/gdpeval/responses.py` as `gdpeval.responses`

### Critical Requirements

1. **`__init__.py` MUST be uploaded**: Without it, Python won't recognize the directory as a package and relative imports will fail with `ImportError: attempted relative import with no known parent package`

2. **Pydantic MUST be installed**: Response models use Pydantic. E2B sandboxes typically have it, but verify or add to sandbox setup:
   ```python
   await sandbox.commands.run("pip install pydantic")
   ```

3. **Don't run skills directly**: Running `python /skills/gdpeval/read_pdf.py` directly would fail because there's no package context. We MUST import it: `from gdpeval.read_pdf import main`

### What Would Break

```python
# ❌ WRONG - direct execution, no package context
await sandbox.commands.run("python /skills/gdpeval/read_pdf.py")

# ❌ WRONG - exec without proper import
code = open('/skills/gdpeval/read_pdf.py').read()
exec(code)  # Relative imports will fail!

# ✅ CORRECT - proper import establishes package context
from gdpeval.read_pdf import main
```

---

## Key Design Decisions

1. **Explicit wrappers over metadata dicts**: Each tool is a real function with real type hints.
   The OpenAI SDK reads these directly - no runtime annotation injection needed.

2. **`skills_dir` over `benchmark` enum**: More flexible. The sandbox doesn't need to know
   about benchmark concepts - it just copies a directory and runs skills from it.

3. **File-based IPC over stdout parsing**: Writing kwargs/results to temp files avoids
   escaping issues and makes debugging easier (can inspect files in sandbox).

4. **Relative imports for typed responses**: Skills use `from .responses import XResponse`
   which works in both VM and local contexts. This means:
   - Skills return typed dataclasses, not plain dicts
   - Agent-written code can import and use the same types
   - Full IDE support when chaining tools

5. **Generic `run_skill[T]()` for type safety**: The return type is a generic parameter,
   so callers get full type checking:
   ```python
   result = await manager.run_skill(run_id, "read_pdf", ReadPDFResponse, file_path="...")
   # result is ReadPDFResponse, IDE knows result.text exists
   ```

6. **Pydantic everywhere**: Skills use Pydantic models for responses. This gives us:
   - `.model_dump()` for serialization
   - `.model_validate()` for parsing
   - Full validation
   - Consistent with rest of codebase
   - E2B sandboxes have Pydantic pre-installed

