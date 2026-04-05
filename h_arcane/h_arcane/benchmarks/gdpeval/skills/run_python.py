"""Run Python skill - executes Python code in the sandbox."""

import sys
import io
import traceback

from .responses import RunPythonResponse


async def main(code: str) -> RunPythonResponse:
    """
    Execute Python code and capture output.

    Args:
        code: Python code to execute

    Returns:
        RunPythonResponse with stdout, stderr, and return value
    """
    # Capture stdout and stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()

    try:
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr

        # Create execution namespace
        exec_globals: dict = {"__builtins__": __builtins__}
        exec_locals: dict = {}

        # Execute the code
        exec(code, exec_globals, exec_locals)

        # Get return value if there's a 'result' variable
        return_value = None
        if "result" in exec_locals:
            return_value = str(exec_locals["result"])

        return RunPythonResponse(
            success=True,
            stdout=captured_stdout.getvalue() or None,
            stderr=captured_stderr.getvalue() or None,
            return_value=return_value,
        )

    except Exception as e:
        error_tb = traceback.format_exc()
        return RunPythonResponse(
            success=False,
            error=str(e),
            stdout=captured_stdout.getvalue() or None,
            stderr=error_tb,
        )

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
