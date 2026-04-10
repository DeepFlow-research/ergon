"""Network discovery: find a reachable IP for the local machine.

Used by ``arcane train launch`` to auto-populate Inngest and DB URLs
that remote VMs can reach.
"""

import logging
import socket
import subprocess

logger = logging.getLogger(__name__)


def discover_reachable_ip() -> str | None:
    """Try to find a non-localhost IP for the local machine.

    Checks Tailscale first (most reliable for remote VMs),
    then falls back to the default network interface.
    Returns None if no reachable IP can be determined.
    """
    tailscale_ip = _try_tailscale()
    if tailscale_ip:
        return tailscale_ip

    return _try_default_interface()


def _try_tailscale() -> str | None:
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ip = result.stdout.strip()
            logger.info("Discovered Tailscale IP: %s", ip)
            return ip
    except FileNotFoundError:
        logger.debug("Tailscale not installed")
    except subprocess.TimeoutExpired:
        logger.debug("Tailscale IP lookup timed out")
    return None


def _try_default_interface() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        logger.info("Discovered default interface IP: %s", ip)
        return ip
    except OSError:
        logger.debug("Could not determine default interface IP")
        return None
    finally:
        s.close()
