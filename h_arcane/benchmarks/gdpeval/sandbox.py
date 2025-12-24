"""GDPEval-specific sandbox manager with Python package dependencies."""

from logging import getLogger
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox

from h_arcane.core.infrastructure.sandbox import BaseSandboxManager

logger = getLogger(__name__)


class GDPEvalSandboxManager(BaseSandboxManager):
    """Sandbox manager for GDPEval benchmark.

    Installs Python packages needed for code rule evaluation:
    - pdfplumber, PyPDF2, reportlab: PDF processing
    - pytesseract: OCR support
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Install Python packages for GDPEval code rules."""
        logger.info(f"Installing GDPEval packages (run_id={run_id})...")

        # E2B default has: numpy, pandas, matplotlib, sklearn, scipy, openpyxl, docx, seaborn, plotly
        # Need: pdfplumber, PyPDF2, reportlab, pytesseract
        pip_result = await sandbox.commands.run(
            "pip install -q pdfplumber PyPDF2 reportlab pytesseract"
        )
        if pip_result.exit_code != 0:
            error_msg = (
                f"Failed to install GDPEval packages (pdfplumber, PyPDF2, reportlab, pytesseract) "
                f"for run_id={run_id}. Exit code: {pip_result.exit_code}. "
                f"Stderr: {pip_result.stderr if pip_result.stderr else 'N/A'}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"Successfully installed GDPEval packages (run_id={run_id})")

    async def _verify_setup(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Verify GDPEval packages are importable."""
        logger.info(f"Verifying GDPEval package installation (run_id={run_id})...")

        verify_code = """
import sys
packages = ['pdfplumber', 'PyPDF2', 'reportlab']
missing = []
for pkg in packages:
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    print(f"MISSING: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)
print("All GDPEval packages verified successfully")
"""
        verify_result = await sandbox.run_code(verify_code, language="python", timeout=10)

        if verify_result.error is not None:
            stderr_text = "N/A"
            if verify_result.logs and verify_result.logs.stderr:
                stderr_parts = list(verify_result.logs.stderr)
                stderr_text = "\n".join(stderr_parts) if stderr_parts else "N/A"
            error_msg = (
                f"GDPEval package verification failed for run_id={run_id}. "
                f"Error: {verify_result.error}, Stderr: {stderr_text}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"GDPEval package verification passed (run_id={run_id})")
