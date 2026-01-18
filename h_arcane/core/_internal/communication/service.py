"""Communication Service - manages inter-agent messaging."""

from uuid import UUID

from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.communication.schemas import (
    CreateMessageRequest,
    MessageResponse,
    ThreadSummary,
    ThreadWithMessages,
    ThreadListResponse,
)


class CommunicationService:
    """Service for managing agent-to-agent communication."""

    def save_message(self, request: CreateMessageRequest) -> MessageResponse:
        """Save a new message, creating thread if needed.

        Args:
            request: The message creation request containing run_id, experiment_id,
                     sender, recipient, topic, and content.

        Returns:
            MessageResponse with the created message details.
        """
        # Get or create thread
        thread = queries.threads.get_or_create_thread(
            run_id=request.run_id,
            experiment_id=request.experiment_id,
            agent_a_id=request.from_agent_id,
            agent_b_id=request.to_agent_id,
            topic=request.thread_topic,
        )

        # Create message
        message = queries.thread_messages.create_message(
            thread_id=thread.id,
            run_id=request.run_id,
            experiment_id=request.experiment_id,
            from_agent_id=request.from_agent_id,
            to_agent_id=request.to_agent_id,
            content=request.content,
        )

        # Update thread timestamp
        queries.threads.update_timestamp(thread.id)

        return MessageResponse(
            message_id=message.id,
            thread_id=thread.id,
            run_id=message.run_id,
            experiment_id=message.experiment_id,
            thread_topic=thread.topic,
            from_agent_id=message.from_agent_id,
            to_agent_id=message.to_agent_id,
            content=message.content,
            sequence_num=message.sequence_num,
            created_at=message.created_at,
        )

    def get_message(self, message_id: UUID) -> MessageResponse | None:
        """Get a message by ID.

        Args:
            message_id: The UUID of the message to retrieve.

        Returns:
            MessageResponse if found, None otherwise.
        """
        message = queries.thread_messages.get(message_id)
        if message is None:
            return None

        thread = queries.threads.get(message.thread_id)
        if thread is None:
            return None

        return MessageResponse(
            message_id=message.id,
            thread_id=message.thread_id,
            run_id=message.run_id,
            experiment_id=message.experiment_id,
            thread_topic=thread.topic,
            from_agent_id=message.from_agent_id,
            to_agent_id=message.to_agent_id,
            content=message.content,
            sequence_num=message.sequence_num,
            created_at=message.created_at,
        )

    def get_thread_messages(self, thread_id: UUID) -> ThreadWithMessages | None:
        """Get all messages in a specific thread.

        Args:
            thread_id: The UUID of the thread to retrieve messages from.

        Returns:
            ThreadWithMessages containing the thread and all its messages,
            or None if the thread doesn't exist.
        """
        thread = queries.threads.get(thread_id)
        if thread is None:
            return None

        messages = queries.thread_messages.get_by_thread(thread_id)

        return ThreadWithMessages(
            thread_id=thread.id,
            run_id=thread.run_id,
            experiment_id=thread.experiment_id,
            topic=thread.topic,
            agent_a_id=thread.agent_a_id,
            agent_b_id=thread.agent_b_id,
            messages=[
                MessageResponse(
                    message_id=m.id,
                    thread_id=m.thread_id,
                    run_id=m.run_id,
                    experiment_id=m.experiment_id,
                    thread_topic=thread.topic,
                    from_agent_id=m.from_agent_id,
                    to_agent_id=m.to_agent_id,
                    content=m.content,
                    sequence_num=m.sequence_num,
                    created_at=m.created_at,
                )
                for m in messages
            ],
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )

    def get_all_threads_between_agents(
        self,
        agent_a_id: str,
        agent_b_id: str,
    ) -> ThreadListResponse:
        """Get all threads between two agents.

        Args:
            agent_a_id: ID of the first agent (e.g. "{run_id}:worker").
            agent_b_id: ID of the second agent (e.g. "{run_id}:stakeholder").

        Returns:
            ThreadListResponse containing summaries of all threads between
            the two agents, ordered by most recently updated first.
        """
        threads = queries.threads.get_threads_between_agents(agent_a_id, agent_b_id)

        summaries = []
        for thread in threads:
            message_count = queries.thread_messages.count_by_thread(thread.id)
            summaries.append(
                ThreadSummary(
                    thread_id=thread.id,
                    run_id=thread.run_id,
                    experiment_id=thread.experiment_id,
                    topic=thread.topic,
                    agent_a_id=thread.agent_a_id,
                    agent_b_id=thread.agent_b_id,
                    message_count=message_count,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                )
            )

        return ThreadListResponse(
            threads=summaries,
            total_count=len(summaries),
        )


# Module-level singleton instance
communication_service = CommunicationService()
