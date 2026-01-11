"""Infrastructure domain - sandbox, Inngest client, and cleanup.

This domain handles:
- Sandbox management (BaseSandboxManager)
- Inngest client configuration
- Infrastructure cleanup (run_cleanup)

Structure:
- sandbox.py: BaseSandboxManager and related types
- inngest_client.py: Inngest client singleton
- inngest_functions.py: run_cleanup
- events.py: RunCleanupEvent

Note: Import inngest_functions directly to avoid circular imports:
    from h_arcane.core.infrastructure.inngest_functions import run_cleanup
"""

# Only export non-circular imports at module level
from h_arcane.core.infrastructure.events import RunCleanupEvent
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.infrastructure.sandbox import (
    BaseSandboxManager,
    DownloadedFile,
    DownloadedFiles,
)

__all__ = [
    # Sandbox
    "BaseSandboxManager",
    "DownloadedFile",
    "DownloadedFiles",
    # Inngest
    "inngest_client",
    # Events
    "RunCleanupEvent",
]
