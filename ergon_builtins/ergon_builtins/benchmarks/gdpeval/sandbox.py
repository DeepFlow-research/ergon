"""GDPEval-specific sandbox manager.

Thin subclass of :class:`BaseSandboxManager` that installs the Python
packages needed for GDP document-processing evaluation (PDF, OCR, etc.).
"""

import logging
from uuid import UUID

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

try:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = object  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_GDP_PACKAGES = "pdfplumber PyPDF2 reportlab pytesseract"


class GDPEvalSandboxManager(BaseSandboxManager):
    """Sandbox manager for the GDPEval benchmark.

    Installs additional Python packages on top of the E2B default image:
    ``pdfplumber``, ``PyPDF2``, ``reportlab``, ``pytesseract``.
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        logger.info("Installing GDPEval packages (task_id=%s) …", task_id)

        pip_result = await sandbox.commands.run(f"pip install -q {_GDP_PACKAGES}")
        if pip_result.exit_code != 0:
            stderr = pip_result.stderr if pip_result.stderr else "N/A"
            raise RuntimeError(
                f"Failed to install GDPEval packages ({_GDP_PACKAGES}) "
                f"for task_id={task_id}. "
                f"exit_code={pip_result.exit_code}, stderr={stderr}"
            )

        logger.info("Successfully installed GDPEval packages (task_id=%s)", task_id)

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        logger.info("Verifying GDPEval package installation (task_id=%s) …", task_id)

        verify_code = (
            "import sys\n"
            "packages = ['pdfplumber', 'PyPDF2', 'reportlab']\n"
            "missing = []\n"
            "for pkg in packages:\n"
            "    try:\n"
            "        __import__(pkg)\n"
            "    except ImportError:\n"
            "        missing.append(pkg)\n"
            "if missing:\n"
            "    print(f'MISSING: {', '.join(missing)}', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "print('All GDPEval packages verified successfully')\n"
        )

        result = await sandbox.run_code(verify_code, language="python", timeout=10)

        if result.error is not None:
            stderr_text = "N/A"
            if result.logs and result.logs.stderr:
                parts = list(result.logs.stderr)
                stderr_text = "\n".join(parts) if parts else "N/A"
            raise RuntimeError(
                f"GDPEval package verification failed for task_id={task_id}. "
                f"error={result.error}, stderr={stderr_text}"
            )

        logger.info("GDPEval package verification passed (task_id=%s)", task_id)
