from ergon_core.api.results import WorkerOutput
from ergon_core.core.runtime.inngest.worker_execute import _worker_execute_result_from_output


def test_worker_execute_result_preserves_worker_output_failure() -> None:
    result = _worker_execute_result_from_output(
        WorkerOutput(output="probe failed", success=False),
    )

    assert result.success is False
    assert result.final_assistant_message == "probe failed"
    assert result.error == "probe failed"
