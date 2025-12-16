"""Execute tool functions inside E2B sandbox."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from h_arcane.agents.sandbox import SandboxManager

# Global run_id for current execution context
_current_run_id: UUID | None = None


def set_sandbox_manager(sandbox_manager: SandboxManager, run_id: UUID) -> None:
    """Set the global run_id for the current execution context."""
    global _current_run_id
    _current_run_id = run_id


def get_sandbox_manager() -> SandboxManager:
    """Get the singleton SandboxManager instance."""
    return SandboxManager()


def get_current_run_id() -> UUID:
    """Get the current run_id for sandbox operations."""
    if _current_run_id is None:
        raise RuntimeError("No run_id set. Call set_sandbox_manager() first.")
    return _current_run_id


def _resolve_paths_in_kwargs(kwargs: dict[str, Any], run_id: UUID) -> dict[str, Any]:
    """Resolve local file paths to sandbox paths in kwargs."""
    sandbox_manager = get_sandbox_manager()
    resolved = {}

    for key, value in kwargs.items():
        # If value is a string path and exists in registry, replace with sandbox path
        if isinstance(value, str) and "path" in key.lower():
            sandbox_path = sandbox_manager.get_sandbox_path(run_id, value)
            if sandbox_path:
                resolved[key] = sandbox_path
            else:
                # Try to resolve relative paths or paths that might be in /inputs or /workspace
                resolved[key] = value
        else:
            resolved[key] = value

    return resolved


async def execute_in_sandbox(tool_name: str, **kwargs) -> dict[str, Any]:
    """
    Execute a tool function inside the sandbox.

    Args:
        tool_name: Name of the tool module (e.g., "read_pdf")
        **kwargs: Arguments to pass to the tool function

    Returns:
        Result dict from tool execution
    """
    run_id = get_current_run_id()
    sandbox_manager = get_sandbox_manager()
    sandbox = sandbox_manager.get_sandbox(run_id)

    if not sandbox:
        raise RuntimeError(
            f"Sandbox not created for run_id={run_id}. Call sandbox_manager.create(run_id) first."
        )

    # Resolve file paths in kwargs to sandbox paths
    resolved_kwargs = _resolve_paths_in_kwargs(kwargs, run_id)

    # Generate Python code to import and execute tool module
    # Tools are uploaded to /tools/ directory in sandbox
    # Formal math tools are in /tools/formal_math/
    # Build code to execute tool
    kwargs_json = json.dumps(resolved_kwargs, default=str)

    # Check if this is a formal_math tool (lean_write, lean_check, lean_verify)
    formal_math_tools = {"write_lean_file", "check_lean_file", "verify_lean_proof"}
    if tool_name in formal_math_tools:
        # Import from formal_math subdirectory
        import_path = f"formal_math.{tool_name}"
    else:
        # Import from root tools directory
        import_path = tool_name

    code = f"""
import json
import sys
sys.path.insert(0, '/tools')

# Import tool module
from {import_path} import {tool_name}

# Execute tool with kwargs
kwargs = json.loads({json.dumps(kwargs_json)})
result = await {tool_name}(**kwargs)

# Convert Pydantic model to dict if needed
if hasattr(result, 'model_dump'):
    result_dict = result.model_dump()
elif hasattr(result, 'dict'):
    result_dict = result.dict()
else:
    result_dict = result

# Output result as JSON
print(json.dumps(result_dict))
"""

    # Execute code in sandbox
    execution = await sandbox.run_code(code, language="python")

    # Parse JSON result from stdout
    if execution.error:
        error_msg = (
            str(execution.error.value)
            if hasattr(execution.error, "value")
            else str(execution.error)
        )
        return {
            "success": False,
            "error": error_msg,
        }

    # Collect stdout
    stdout_parts = []
    if execution.logs:
        for log in execution.logs.stdout:
            stdout_parts.append(log)

    stdout_text = "\n".join(stdout_parts)

    # Try to parse JSON from stdout
    try:
        # Find JSON in stdout (might have other output)
        lines = stdout_text.strip().split("\n")
        json_line = None
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") or line.startswith("["):
                json_line = line
                break

        if json_line:
            result = json.loads(json_line)
        else:
            result = {
                "success": False,
                "error": f"No JSON output found. Stdout: {stdout_text[:200]}",
            }
    except json.JSONDecodeError as e:
        result = {
            "success": False,
            "error": f"Failed to parse JSON result: {e}. Stdout: {stdout_text[:200]}",
        }

    return result


async def upload_tools_to_sandbox(sandbox_manager: SandboxManager, run_id: UUID) -> None:
    """Upload all tool modules from h_arcane/tools/ to /tools/ in sandbox."""
    sandbox = sandbox_manager.get_sandbox(run_id)
    if not sandbox:
        raise RuntimeError(f"Sandbox not created for run_id={run_id}. Call create(run_id) first.")

    tools_dir = Path(__file__).parent.parent / "tools"
    if not tools_dir.exists():
        # Tools directory doesn't exist yet (will be created in Phase 2.2)
        return

    # /tools directory should already be created in sandbox_manager.create()
    # But verify it exists and is writable, create if needed
    try:
        # Try to write a test file to verify /tools exists and is writable
        await sandbox.files.write("/tools/.test_write", b"test")
        await sandbox.commands.run("rm -f /tools/.test_write")
    except Exception:
        # If /tools doesn't exist or isn't writable, create it using Python
        create_tools_code = """
import os
import stat
os.makedirs('/tools', exist_ok=True)
try:
    os.chmod('/tools', stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
except Exception:
    pass
"""
        tools_result = await sandbox.run_code(create_tools_code, language="python")
        if tools_result.error:
            raise RuntimeError(f"Failed to create /tools directory: {tools_result.error}")

    # Upload responses.py first (needed by tool modules)
    responses_file = tools_dir / "responses.py"
    if responses_file.exists():
        await sandbox.files.write("/tools/responses.py", responses_file.read_bytes())

    # Upload formal_math tools if they exist
    formal_math_dir = tools_dir / "formal_math"
    if formal_math_dir.exists():
        # Ensure /tools/formal_math directory exists in sandbox
        create_formal_math_code = """
import os
import stat
os.makedirs('/tools/formal_math', exist_ok=True)
try:
    os.chmod('/tools/formal_math', stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
except Exception:
    pass
"""
        formal_math_result = await sandbox.run_code(create_formal_math_code, language="python")
        if formal_math_result.error:
            raise RuntimeError(
                f"Failed to create /tools/formal_math directory: {formal_math_result.error}"
            )

        # Upload formal_math/responses.py (needed by tool modules)
        formal_responses = formal_math_dir / "responses.py"
        if formal_responses.exists():
            await sandbox.files.write(
                "/tools/formal_math/responses.py", formal_responses.read_bytes()
            )

        # Upload formal_math/utils.py (needed by some tools)
        formal_utils = formal_math_dir / "utils.py"
        if formal_utils.exists():
            await sandbox.files.write("/tools/formal_math/utils.py", formal_utils.read_bytes())

        # Upload formal_math tool modules
        for tool_file in formal_math_dir.glob("*.py"):
            if tool_file.name in ("__init__.py", "responses.py", "utils.py"):
                continue
            sandbox_path = f"/tools/formal_math/{tool_file.name}"
            content = tool_file.read_bytes()
            await sandbox.files.write(sandbox_path, content)

    # Upload each tool module
    for tool_file in tools_dir.glob("*.py"):
        if tool_file.name in ("__init__.py", "responses.py"):
            continue

        sandbox_path = f"/tools/{tool_file.name}"
        content = tool_file.read_bytes()
        await sandbox.files.write(sandbox_path, content)
