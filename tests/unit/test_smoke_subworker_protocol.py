"""Contract test: anything claiming to be a SmokeSubworker must pass runtime_checkable."""

from ergon_builtins.workers.stubs.smoke_subworker import (
    SmokeSubworker,
    SubworkerResult,
)


def test_subworker_result_is_frozen() -> None:
    r = SubworkerResult(file_path="/tmp/x", probe_stdout="1\n", probe_exit_code=0)
    try:
        r.file_path = "/tmp/y"  # type: ignore[misc]
    except Exception as e:
        assert isinstance(e, Exception)
    else:
        raise AssertionError("SubworkerResult must be frozen")


def test_minimal_async_class_satisfies_protocol() -> None:
    class OK:
        async def work(self, node_id: str, sandbox):  # noqa: ANN001
            return SubworkerResult("/tmp/x", "out", 0)

    assert isinstance(OK(), SmokeSubworker)


def test_missing_work_method_fails_protocol_check() -> None:
    class Bad:
        pass

    assert not isinstance(Bad(), SmokeSubworker)
