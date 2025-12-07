# Sandbox Architecture: Agent Outside, Tools Inside

**Pattern**: Agent orchestrates outside sandbox, all tool execution happens inside sandbox.

**Rationale**: 
- Keep orchestration layer (agent) outside where it can access databases, APIs, IAM roles
- Minimize ephemeral sandbox dependencies (no IAM, no persistent services)
- Full isolation per run for evaluation
- Scalable (one sandbox per run)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent (Outside Sandbox)                  │
│  - OpenAI Agents SDK                                        │
│  - Database access (messages, actions)                     │
│  - Stakeholder communication                               │
│  - Tool orchestration                                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ Tool Calls
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌──────────────┐              ┌──────────────────┐
│ ask_stakeholder│              │ GDPEval Tools    │
│ (HTTP/DB)     │              │ (Sandbox Proxy)  │
└──────────────┘              └────────┬─────────┘
                                       │
                                       │ Execute in Sandbox
                                       │
                                       ▼
                        ┌──────────────────────────┐
                        │   E2B Sandbox (Per Run)  │
                        │                          │
                        │  /inputs/                │
                        │  /workspace/             │
                        │  (all tool operations)   │
                        └──────────────────────────┘
```

---

## Core Components

### 1. SandboxManager

**Purpose**: Lifecycle management of E2B sandbox per run.

```python
from e2b_code_interpreter.code_interpreter_async import AsyncSandbox
from uuid import UUID
from pathlib import Path

class SandboxManager:
    """Manages E2B sandbox lifecycle for a single run."""
    
    def __init__(self, run_id: UUID):
        self.run_id = run_id
        self.sandbox: AsyncSandbox | None = None
        self._file_registry: dict[str, str] = {}  # local_path -> sandbox_path
        self._created_files: set[str] = []  # sandbox paths created by tools
    
    async def create(self) -> None:
        """Create and initialize sandbox."""
        self.sandbox = await AsyncSandbox.create()
        
        # Create directory structure
        await self.sandbox.commands.run("mkdir -p /inputs")
        await self.sandbox.commands.run("mkdir -p /workspace")
        
        # Install missing tool dependencies
        # E2B default has: numpy, pandas, matplotlib, sklearn, scipy, openpyxl, docx, seaborn, plotly
        # Need: pdfplumber, PyPDF2, reportlab, pytesseract
        await self.sandbox.commands.run(
            "pip install -q pdfplumber PyPDF2 reportlab pytesseract"
        )
    
    async def upload_inputs(self, resources: list[Resource]) -> None:
        """Upload input resources to /inputs/."""
        for resource in resources:
            sandbox_path = f"/inputs/{resource.name}"
            content = resource.load_content()
            await self.sandbox.files.write(sandbox_path, content)
            self._file_registry[resource.file_path] = sandbox_path
    
    async def upload_file(self, local_path: str, sandbox_path: str) -> None:
        """Upload a single file to sandbox."""
        content = Path(local_path).read_bytes()
        await self.sandbox.files.write(sandbox_path, content)
        self._file_registry[local_path] = sandbox_path
    
    async def download_file(self, sandbox_path: str) -> bytes:
        """Download a file from sandbox."""
        return await self.sandbox.files.read(sandbox_path)
    
    async def list_files(self, sandbox_dir: str = "/workspace") -> list[str]:
        """List files in sandbox directory."""
        # Use find command to list files recursively
        result = await self.sandbox.commands.run(f"find {sandbox_dir} -type f 2>/dev/null || true")
        if result.exit_code != 0:
            return []
        # Parse output - each line is a file path
        files = [line.strip() for line in result.stdout.split("\n") if line.strip()]
        return files
    
    async def download_all_outputs(self, output_dir: Path) -> list[dict]:
        """Download all files from /workspace to output_dir."""
        files = await self.list_files("/workspace")
        downloaded = []
        
        for file_path in files:
            content = await self.download_file(file_path)
            local_path = output_dir / Path(file_path).name
            local_path.write_bytes(content)
            downloaded.append({
                "sandbox_path": file_path,
                "local_path": str(local_path),
                "size_bytes": len(content),
            })
        
        return downloaded
    
    async def terminate(self) -> None:
        """Terminate sandbox."""
        if self.sandbox:
            await self.sandbox.close()
            self.sandbox = None
```

**Key Design Decisions:**
- One sandbox per run (created at start, terminated at end)
- Inputs go to `/inputs/`, outputs go to `/workspace/`
- File registry tracks local ↔ sandbox path mapping
- Created files tracked for final download

---

### 2. Tool Module Structure

**Purpose**: Standard tool modules that work both locally and in sandbox.

**Structure**: Each tool is a standalone Python module with a pure function.

```python
# h_arcane/tools/read_pdf.py
"""Read PDF tool - works in sandbox or locally."""
import pdfplumber
from pathlib import Path

async def read_pdf(file_path: str) -> dict:
    """
    Extract text from PDF file with page markers.
    
    Args:
        file_path: Path to PDF file
    
    Returns:
        dict with 'success' bool and 'text' or 'error'
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return {"success": False, "error": f"PDF file not found at {file_path}"}
        
        extracted_text = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    extracted_text.append(f"--- Page {page_num} ---\n{text}")
        
        if not extracted_text:
            return {"success": False, "error": "No text could be extracted from the PDF"}
        
        return {"success": True, "text": "\n\n".join(extracted_text)}
    except Exception as e:
        return {"success": False, "error": f"Error reading PDF: {str(e)}"}
```

```python
# h_arcane/tools/create_docx.py
"""Create DOCX tool - works in sandbox or locally."""
from docx import Document
from pathlib import Path

async def create_docx(
    content: str,
    output_path: str,
    title: str | None = None
) -> dict:
    """
    Create DOCX file from markdown content.
    
    Args:
        content: Markdown content
        output_path: Path to save DOCX file
        title: Optional document title
    
    Returns:
        dict with 'success' bool and 'path' or 'error'
    """
    try:
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        doc = Document()
        if title:
            doc.add_heading(title, 0)
        
        # Simple markdown parsing
        for line in content.split('\n'):
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text = line.lstrip('# ').strip()
                doc.add_heading(text, level=min(level, 3))
            elif line.strip():
                doc.add_paragraph(line.strip())
        
        doc.save(output_path)
        return {"success": True, "path": output_path}
    except Exception as e:
        return {"success": False, "error": f"Error creating DOCX: {str(e)}"}
```

### 3. Sandbox Execution Function

```python
# h_arcane/agents/sandbox_executor.py
"""Common function to execute tools in sandbox."""
import json
from pathlib import Path
from typing import Any

# Global sandbox manager (set at task start)
_sandbox_manager: SandboxManager | None = None

def set_sandbox_manager(sandbox_manager: SandboxManager) -> None:
    """Set the sandbox manager for this run."""
    global _sandbox_manager
    _sandbox_manager = sandbox_manager

async def execute_in_sandbox(tool_name: str, **kwargs) -> dict[str, Any]:
    """
    Execute a tool function inside sandbox.
    
    Args:
        tool_name: Name of tool module (e.g., 'read_pdf')
        **kwargs: Arguments to pass to tool function
    
    Returns:
        Tool result dict with 'success' bool and result fields or 'error'
    """
    if _sandbox_manager is None:
        raise RuntimeError("Sandbox manager not set. Call set_sandbox_manager() first.")
    
    sandbox = _sandbox_manager.sandbox
    file_registry = _sandbox_manager._file_registry
    
    # Resolve file paths in kwargs
    resolved_kwargs = _resolve_paths_in_kwargs(kwargs, file_registry)
    
    # Serialize kwargs to JSON (handle special types)
    kwargs_json = json.dumps(resolved_kwargs, default=str)
    
    # Generate code to import and execute tool
    code = f"""
import sys
sys.path.insert(0, '/tools')
import json
import asyncio
from {tool_name} import {tool_name}

# Parse arguments
kwargs = json.loads('''{kwargs_json}''')

# Execute tool (handle both sync and async)
try:
    import inspect
    if inspect.iscoroutinefunction({tool_name}):
        result = asyncio.run({tool_name}(**kwargs))
    else:
        result = {tool_name}(**kwargs)
except Exception as e:
    result = {{"success": False, "error": str(e)}}

# Return as JSON
print(json.dumps(result))
"""
    
    # Execute in sandbox
    execution = await sandbox.run_code(code, language="python", timeout=60)
    
    # Parse result from stdout
    output = "\n".join(execution.logs.stdout) if execution.logs else ""
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        # If no JSON, check stderr for errors
        error_output = "\n".join(execution.logs.stderr) if execution.logs else ""
        if execution.error:
            error_output = f"{error_output}\n{str(execution.error)}"
        return {"success": False, "error": f"Failed to parse result: {error_output}"}
    
    if not result.get("success"):
        raise ValueError(result.get("error", "Tool execution failed"))
    
    # Track created files if output_path in kwargs
    if "output_path" in resolved_kwargs:
        output_path = resolved_kwargs["output_path"]
        if output_path.startswith("/workspace/"):
            _sandbox_manager._created_files.add(output_path)
    
    return result

def _resolve_paths_in_kwargs(kwargs: dict, file_registry: dict[str, str]) -> dict:
    """Resolve file paths in kwargs to sandbox paths."""
    resolved = {}
    for key, value in kwargs.items():
        if key.endswith("_path") or key == "file_path" or key == "output_path":
            resolved[key] = _resolve_sandbox_path(value, file_registry)
        else:
            resolved[key] = value
    return resolved

def _resolve_sandbox_path(file_path: str, file_registry: dict[str, str]) -> str:
    """Resolve file path to sandbox path."""
    # If already a sandbox path, return as-is
    if file_path.startswith("/inputs/") or file_path.startswith("/workspace/"):
        return file_path
    
    # If local path, check registry
    if file_path in file_registry:
        return file_registry[file_path]
    
    # For output paths, default to /workspace/
    if file_path.startswith("/tmp/") or (file_path.startswith("/") and not file_path.startswith("/home")):
        # Absolute local path - extract filename, put in workspace
        return f"/workspace/{Path(file_path).name}"
    
    # Relative path - default to /workspace/
    return f"/workspace/{file_path}"
```

### 4. Tool Functions (with sandbox execution)

**Purpose**: Each tool is a `@function_tool` that internally calls `execute_in_sandbox()`.

```python
# h_arcane/agents/tools.py
"""Tool functions for agent - execute in sandbox."""
from agents import function_tool
from h_arcane.agents.sandbox_executor import execute_in_sandbox

@function_tool
async def read_pdf(file_path: str) -> str:
    """
    Extract text content from a PDF file with page markers for easy navigation.

    This tool reads PDF files and extracts all text content, inserting page markers
    (e.g., "--- Page 1 ---") to help you identify which page text came from.

    Parameters:
        file_path (str):
            The absolute or relative path to the PDF file to read.
            Example: "/path/to/document.pdf" or "reports/quarterly_report.pdf"

    Returns:
        str:
            The full text content of the PDF with page markers, or an error message if
            the file cannot be read or contains no extractable text.
    """
    result = await execute_in_sandbox("read_pdf", file_path=file_path)
    if "text" in result:
        return result["text"]
    else:
        raise ValueError(result.get("error", "Failed to read PDF"))

@function_tool
async def create_docx(
    content: str,
    output_path: str,
    title: str | None = None
) -> str:
    """
    Create a Word document (DOCX) from markdown content.

    Parameters:
        content (str): Markdown-formatted content
        output_path (str): Path where the DOCX file should be saved
        title (str, optional): Document title

    Returns:
        str: Success message with file path
    """
    result = await execute_in_sandbox(
        "create_docx",
        content=content,
        output_path=output_path,
        title=title
    )
    if "path" in result:
        return f"✅ Created DOCX: {result['path']}"
    else:
        raise ValueError(result.get("error", "Failed to create DOCX"))
```

---

## File Synchronization

**Single sandbox per run** - files persist between tool calls. No download/reupload needed until end of run.

---

---

## Error Handling

- Sandbox creation fails → Retry, mark run FAILED
- Tool execution fails → Parse error, return to agent (agent can retry)
- File upload/download fails → Retry with backoff
- Sandbox timeout → Monitor, add checkpointing if needed (future)
- Always terminate sandbox in `finally` block

---

---

## Integration

```python
# h_arcane/agents/sandbox_executor.py
async def upload_tools_to_sandbox(sandbox_manager: SandboxManager) -> None:
    """Upload tool modules to sandbox at /tools/."""
    sandbox = sandbox_manager.sandbox
    tools_dir = Path(__file__).parent.parent / "tools"
    
    # Create /tools directory
    await sandbox.commands.run("mkdir -p /tools")
    
    # Upload each tool module
    for tool_file in tools_dir.glob("*.py"):
        sandbox_path = f"/tools/{tool_file.name}"
        content = tool_file.read_bytes()
        await sandbox.files.write(sandbox_path, content)
    
    # Create __init__.py
    await sandbox.files.write(
        "/tools/__init__.py",
        b"# Tools module"
    )
```

### WorkerToolkit

```python
class WorkerToolkit:
    def __init__(
        self,
        run_id: UUID,
        stakeholder: RubricStakeholder,
        sandbox_manager: SandboxManager,  # NEW
        max_questions: int = 10,
    ):
        self.run_id = run_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
    
    def get_gdpeval_tools(self) -> list[Tool]:
        """Get GDPEval tools that execute in sandbox."""
        # Set sandbox manager for execute_in_sandbox()
        from h_arcane.agents.sandbox_executor import set_sandbox_manager
        set_sandbox_manager(self.sandbox_manager)
        
        # Import tool functions (they're already @function_tool decorated)
        from h_arcane.agents.tools import (
            read_pdf,
            create_docx,
            read_excel,
            create_excel,
            # ... etc
        )
        
        return [
            read_pdf,
            create_docx,
            read_excel,
            create_excel,
            # ... etc
        ]
```

### worker_execute()

```python
async def worker_execute(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    run_id = UUID(ctx.event.data["run_id"])
    
    # Load state
    run = await step.run("load-run", lambda: queries.runs.get(run_id))
    experiment = await step.run("load-experiment", ...)
    input_resources = await step.run("load-resources", ...)
    
    # Create sandbox
    sandbox_manager = SandboxManager(run_id)
    await step.run("create-sandbox", lambda: sandbox_manager.create())
    
    try:
        # Upload inputs
        await step.run(
            "upload-inputs",
            lambda: sandbox_manager.upload_inputs(input_resources)
        )
        
        # Upload tools to sandbox (before creating toolkit)
        from h_arcane.agents.sandbox_executor import upload_tools_to_sandbox
        await step.run("upload-tools", lambda: upload_tools_to_sandbox(sandbox_manager))
        
        # Set sandbox manager for execute_in_sandbox()
        from h_arcane.agents.sandbox_executor import set_sandbox_manager
        await step.run("set-sandbox-manager", lambda: set_sandbox_manager(sandbox_manager))
        
        # Create toolkit with sandbox
        toolkit = WorkerToolkit(
            run_id=run_id,
            stakeholder=stakeholder,
            sandbox_manager=sandbox_manager,
            max_questions=run.max_questions,
        )
        
        # Execute worker (tools will use sandbox)
        worker = ReActWorker(model=run.worker_model)
        execution_output = await step.run(
            "execute-task",
            lambda: worker.execute(
                run_id=run_id,
                task_description=experiment.task_description,
                input_resources=input_resources,
                toolkit=toolkit,
            )
        )
        
        # Download all outputs
        output_dir = Path(f"data/runs/{run_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded_files = await step.run(
            "download-outputs",
            lambda: sandbox_manager.download_all_outputs(output_dir)
        )
        
        # Register downloaded files as Resources
        for file_info in downloaded_files:
            await step.run(
                f"register-resource-{file_info['local_path']}",
                lambda fi=file_info: queries.resources.create(
                    run_id=run_id,
                    name=Path(fi["local_path"]).name,
                    mime_type=get_mime_type(fi["local_path"]),
                    file_path=fi["local_path"],
                    size_bytes=fi["size_bytes"],
                )
            )
        
        # Save output to run
        await step.run("save-output", ...)
        
        # Emit for evaluation
        await step.invoke(inngest.Event(name="execution/done", ...))
        
    finally:
        # Always terminate sandbox
        await step.run("terminate-sandbox", lambda: sandbox_manager.terminate())
    
    return {"run_id": str(run_id)}
```

---

## Testing

**High-Risk Areas**: Path resolution, code generation, file state consistency, error propagation, sandbox lifecycle

**Strategy**: Unit tests (path resolution, code generation), integration tests (full tool execution, multi-tool workflows), E2E tests (complete run)

---

## Migration Path

### Phase 1: Infrastructure
1. Implement `SandboxManager` (lifecycle management)
2. Implement `execute_in_sandbox()` function
3. Create first tool module (`h_arcane/tools/read_pdf.py`)
4. Create first tool function (`h_arcane/agents/tools.py` with `read_pdf`)
5. Test in isolation

### Phase 2: Tool Coverage
1. Create all tool modules in `h_arcane/tools/`
2. Create all tool functions in `h_arcane/agents/tools.py`
3. All tools call `execute_in_sandbox()` internally
4. Test multi-tool workflows
5. Handle `execute_python_code` to use run's sandbox

### Phase 3: Integration
1. Integrate into `WorkerToolkit`
2. Update `worker_execute()`
3. Test with real experiments

### Phase 4: Optimization
1. Batch file operations
2. Code caching
3. Performance monitoring

---

## Decisions

- **Tool modules**: `h_arcane/tools/` → uploaded to `/tools/` at task start
- **Path resolution**: `execute_in_sandbox()` resolves paths (agent unaware)
- **ResourceFileManager**: Not needed (files managed in sandbox)
- **execute_python_code**: Use run's sandbox (check global sandbox manager)
- **RAG tools**: In-memory index (acceptable trade-off)
- **Tool dependencies**: Install pdfplumber, PyPDF2, reportlab, pytesseract at sandbox creation
- **Sandbox timeout**: Monitor, add checkpointing if needed (future)

---

## Implementation Phases

1. **Infrastructure**: `SandboxManager`, `execute_in_sandbox()`, first tool (`read_pdf`)
2. **Tool Coverage**: Create all tool modules and tool functions
3. **Integration**: Update `worker_execute()`, `WorkerToolkit`
4. **Testing**: Run experiments, monitor performance

