"""Communication service for agent-to-agent messaging."""

from h_arcane.core._internal.communication.service import (
    CommunicationService,
    communication_service,
)
from h_arcane.core._internal.communication.schemas import (
    CreateMessageRequest,
    GetMessageRequest,
    GetThreadMessagesRequest,
    GetAgentThreadsRequest,
    MessageResponse,
    ThreadSummary,
    ThreadWithMessages,
    ThreadListResponse,
)

__all__ = [
    # Service
    "CommunicationService",
    "communication_service",
    # Request schemas
    "CreateMessageRequest",
    "GetMessageRequest",
    "GetThreadMessagesRequest",
    "GetAgentThreadsRequest",
    # Response schemas
    "MessageResponse",
    "ThreadSummary",
    "ThreadWithMessages",
    "ThreadListResponse",
]
