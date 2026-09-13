"""Force two native message sends to read the same sequence in real Postgres."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import event, text

from ergon_core.core.application.communication.models import CreateMessageRequest, MessageResponse
from ergon_core.core.application.communication.service import CommunicationService
from ergon_core.core.persistence.shared.db import get_engine

OUT = Path(__file__).with_name("postgres-result.json")


def main() -> None:
    sample_id = UUID(
        json.loads(Path(__file__).with_name("lifecycle-result.json").read_text())["sample_id"]
    )
    topic = f"sequence-proof-{uuid4().hex[:8]}"
    service = CommunicationService()
    request = CreateMessageRequest(
        sample_id=sample_id,
        from_agent_id="alice",
        to_agent_id="bob",
        thread_topic=topic,
        content="seed",
    )
    seed = asyncio.run(service.save_message(request))
    engine = get_engine()
    barrier = Barrier(2, timeout=15)

    def synchronize_reads(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if "max(thread_messages.sequence_num)" in statement:
            barrier.wait()

    def send(content: str) -> MessageResponse:
        return asyncio.run(service.save_message(request.model_copy(update={"content": content})))

    event.listen(engine, "after_cursor_execute", synchronize_reads)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            messages = list(pool.map(send, ["first concurrent send", "second concurrent send"]))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_reads)
    with engine.connect() as connection:
        version = connection.execute(text("select version()")).scalar_one()
    sequences = [message.sequence_num for message in messages]
    result = {
        "sample_id": str(sample_id),
        "thread_id": str(seed.thread_id),
        "database": version,
        "method": "native service, two threads/connections, barrier after both max(sequence) reads",
        "concurrent_sequences": sequences,
        "unique_sequences": len(set(sequences)) == 2,
        "persisted_message_count": len(service.get_thread_messages(seed.thread_id)),
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
