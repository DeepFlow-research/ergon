from uuid import uuid4

from ergon_core.core.api.runs import _build_communication_threads
from ergon_core.core.persistence.telemetry.models import Thread, ThreadMessage


def test_build_communication_threads_populates_summary_and_task_anchors() -> None:
    run_id = uuid4()
    thread_id = uuid4()
    execution_id = uuid4()
    task_id = uuid4()
    thread = Thread(
        id=thread_id,
        run_id=run_id,
        topic="smoke-completion",
        summary="Leaf workers report completion artifacts and probe exit status.",
        agent_a_id="leaf-l_1",
        agent_b_id="parent",
    )
    message = ThreadMessage(
        thread_id=thread_id,
        run_id=run_id,
        task_execution_id=execution_id,
        from_agent_id="leaf-l_1",
        to_agent_id="parent",
        content="l_1: done exit=0",
        sequence_num=1,
    )

    result = _build_communication_threads(
        [thread],
        [message],
        {execution_id: task_id},
    )

    assert len(result) == 1
    dto = result[0]
    assert dto.summary == "Leaf workers report completion artifacts and probe exit status."
    assert dto.task_id == str(task_id)
    assert dto.messages[0].task_id == str(task_id)
    assert dto.messages[0].task_execution_id == str(execution_id)


def test_build_communication_threads_keeps_run_level_thread_when_messages_span_tasks() -> None:
    run_id = uuid4()
    thread_id = uuid4()
    execution_a = uuid4()
    execution_b = uuid4()
    thread = Thread(
        id=thread_id,
        run_id=run_id,
        topic="smoke-completion",
        agent_a_id="leaf-l_1",
        agent_b_id="parent",
    )
    messages = [
        ThreadMessage(
            thread_id=thread_id,
            run_id=run_id,
            task_execution_id=execution_a,
            from_agent_id="leaf-l_1",
            to_agent_id="parent",
            content="l_1: done exit=0",
            sequence_num=1,
        ),
        ThreadMessage(
            thread_id=thread_id,
            run_id=run_id,
            task_execution_id=execution_b,
            from_agent_id="leaf-l_2",
            to_agent_id="parent",
            content="l_2: done exit=0",
            sequence_num=2,
        ),
    ]

    result = _build_communication_threads(
        [thread],
        messages,
        {execution_a: uuid4(), execution_b: uuid4()},
    )

    assert result[0].task_id is None
