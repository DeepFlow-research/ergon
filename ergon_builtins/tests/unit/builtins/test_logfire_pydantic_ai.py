import importlib


def test_logfire_pydantic_ai_instrumentation_is_disabled_by_default(monkeypatch) -> None:
    module = importlib.import_module("ergon_builtins.observability.pydantic_ai_logfire")
    module._reset_for_tests()
    monkeypatch.delenv("ERGON_LOGFIRE_PYDANTIC_AI", raising=False)

    assert module.configure_pydantic_ai_logfire(logfire_module=_FailingLogfire()) is False


def test_logfire_pydantic_ai_instrumentation_configures_once(monkeypatch) -> None:
    module = importlib.import_module("ergon_builtins.observability.pydantic_ai_logfire")
    module._reset_for_tests()
    monkeypatch.setenv("ERGON_LOGFIRE_PYDANTIC_AI", "1")
    monkeypatch.setenv("ERGON_LOGFIRE_SERVICE_NAME", "ergon-test")
    monkeypatch.setenv("ERGON_LOGFIRE_ENVIRONMENT", "unit")
    monkeypatch.setenv("ERGON_LOGFIRE_CONFIG_DIR", "/tmp/logfire-config")
    fake = _FakeLogfire()

    assert module.configure_pydantic_ai_logfire(logfire_module=fake) is True
    assert module.configure_pydantic_ai_logfire(logfire_module=fake) is True

    assert fake.configure_calls == [
        {
            "send_to_logfire": "if-token-present",
            "service_name": "ergon-test",
            "environment": "unit",
            "config_dir": "/tmp/logfire-config",
            "console": False,
        }
    ]
    assert fake.instrument_calls == [{"include_content": True}]


class _FailingLogfire:
    def configure(self, **kwargs):
        raise AssertionError("disabled instrumentation should not configure Logfire")

    def instrument_pydantic_ai(self, **kwargs):
        raise AssertionError("disabled instrumentation should not instrument pydantic-ai")


class _FakeLogfire:
    def __init__(self) -> None:
        self.configure_calls = []
        self.instrument_calls = []

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)

    def instrument_pydantic_ai(self, **kwargs):
        self.instrument_calls.append(kwargs)
