"""Ergon shim for upstream ``manager_agent_gym.core.communication.service``.

Upstream's in-process message bus is replaced by Ergon's persisted
communication service. The vendored evaluators reference the type only in the
signature of ``build_default_evaluators``, whose argument they never use.
"""


class CommunicationService:
    """Placeholder for upstream's in-process communication service."""
