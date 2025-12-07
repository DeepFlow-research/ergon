"""Execute tool functions inside E2B sandbox."""

import json
from pathlib import Path
from typing import Any

from h_arcane.agents.sandbox import SandboxManager

# Global sandbox manager for current run
_current_sandbox_manager: SandboxManager | None = None


def set_sandbox_manager(sandbox_manager: SandboxManager) -> None:
    """Set the global sandbox manager for the current run."""
    global _current_sandbox_manager
    _current_sandbox_manager = sandbox_manager


def get_sandbox_manager() -> SandboxManager:
    """Get the current sandbox manager."""
    if _current_sandbox_manager is None:
        raise RuntimeError("No sandbox manager set. Call set_sandbox_manager() first.")
    return _current_sandbox_manager


def _resolve_paths_in_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Resolve local file paths to sandbox paths in kwargs."""
    sandbox_manager = get_sandbox_manager()
    resolved = {}

    for key, value in kwargs.items():
        # If value is a string path and exists in registry, replace with sandbox path
        if isinstance(value, str) and "path" in key.lower():
            sandbox_path = sandbox_manager.get_sandbox_path(value)
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
    sandbox_manager = get_sandbox_manager()

    if not sandbox_manager.sandbox:
        raise RuntimeError("Sandbox not created. Call sandbox_manager.create() first.")

    # Resolve file paths in kwargs to sandbox paths
    resolved_kwargs = _resolve_paths_in_kwargs(kwargs)

    # Generate Python code to import and execute tool module
    # Tools are uploaded to /tools/ directory in sandbox
    # Build code to execute tool
    kwargs_json = json.dumps(resolved_kwargs, default=str)
    code = f"""
import json
import sys
sys.path.insert(0, '/tools')

# Import tool module
from {tool_name} import {tool_name}

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
    execution = await sandbox_manager.sandbox.run_code(code, language="python")

    # Parse JSON result from stdout
    if execution.error:
        return {
            "success": False,
            "error": str(execution.error.value)
            if hasattr(execution.error, "value")
            else str(execution.error),
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
            return result
        else:
            return {
                "success": False,
                "error": f"No JSON output found. Stdout: {stdout_text[:200]}",
            }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse JSON result: {e}. Stdout: {stdout_text[:200]}",
        }


async def upload_tools_to_sandbox(sandbox_manager: SandboxManager) -> None:
    """Upload all tool modules from h_arcane/tools/ to /tools/ in sandbox."""
    if not sandbox_manager.sandbox:
        raise RuntimeError("Sandbox not created. Call create() first.")

    tools_dir = Path(__file__).parent.parent / "tools"
    if not tools_dir.exists():
        # Tools directory doesn't exist yet (will be created in Phase 2.2)
        return

    # Create /tools directory in sandbox
    await sandbox_manager.sandbox.commands.run("mkdir -p /tools")

    # Upload responses.py first (needed by tool modules)
    responses_file = tools_dir / "responses.py"
    if responses_file.exists():
        await sandbox_manager.sandbox.files.write(
            "/tools/responses.py", responses_file.read_bytes()
        )

    # Upload each tool module
    for tool_file in tools_dir.glob("*.py"):
        if tool_file.name in ("__init__.py", "responses.py"):
            continue

        sandbox_path = f"/tools/{tool_file.name}"
        content = tool_file.read_bytes()
        await sandbox_manager.sandbox.files.write(sandbox_path, content)
