"""Pre-flight connectivity checks for remote training.

Verifies that Inngest and Postgres are reachable before launching
a training job on a remote VM.
"""

import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def check_training_connectivity(
    inngest_url: str,
    db_url: str,
) -> list[str]:
    """Return a list of warnings about connectivity issues.

    Empty list means all checks passed.
    """
    warnings: list[str] = []

    if "localhost" in inngest_url or "127.0.0.1" in inngest_url:
        warnings.append(
            "Inngest URL points to localhost — remote VMs won't be able to "
            "reach it. Use your Tailscale IP or a public URL."
        )

    if "localhost" in db_url or "127.0.0.1" in db_url:
        warnings.append(
            "Database URL points to localhost — remote VMs won't be able to "
            "reach it. Use your Tailscale IP or a public URL."
        )

    try:
        resp = urllib.request.urlopen(f"{inngest_url}/health", timeout=5)
        if resp.status != 200:
            warnings.append(f"Inngest health check returned HTTP {resp.status}")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        warnings.append(f"Cannot reach Inngest at {inngest_url}: {e}")

    return warnings
