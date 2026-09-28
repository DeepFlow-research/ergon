"""Ergon shim for upstream ``manager_agent_gym.core.common.logging``.

Upstream configures a package-wide logger at import time. The vendored schemas
only use the ``logger`` object, so Ergon provides a standard library logger.
"""

import logging

logger = logging.getLogger("manager_agent_gym")
