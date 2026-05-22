"""Tests for the MiniF2F llama.cpp getting-started example."""

import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from uuid import UUID

import pytest

from getting_started._shared import llamacpp
from getting_started._shared import model_cache
from getting_started._shared import env

_EXAMPLE_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "getting_started"
    / "01_minif2f_local_llamacpp"
    / "run.py"
)


def _load_example_module():
    spec = importlib.util.spec_from_file_location("minif2f_local_llamacpp_run", _EXAMPLE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_uses_packaged_imports_without_repo_root_sys_path_hack() -> None:
    source = _EXAMPLE_PATH.read_text()

    assert "sys.path.insert" not in source
    assert "Path(__file__).resolve().parents" not in source
    assert "from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark" in source
    assert "from getting_started._shared.env import" in source


def test_module_help_and_preflight_failures_do_not_launch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    module = _load_example_module()

    with pytest.raises(SystemExit) as exc_info:
        module.parse_args(["--help"])

    assert exc_info.value.code == 0
    assert "MiniF2F" in capsys.readouterr().out
    assert module.main([]) == 2
    assert "Missing E2B_API_KEY" in capsys.readouterr().err


class _FakeModelsResponse:
    def __init__(self, model_id: str) -> None:
        self._body = json.dumps({"data": [{"id": model_id}]}).encode()

    def __enter__(self) -> "_FakeModelsResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class _ManagedServerStub:
    base_url = "http://127.0.0.1:8123"
    discovered_model = "mini-proof-local"

    def __init__(self, observed: dict[str, object]) -> None:
        self._observed = observed

    def close(self, *, keep_running: bool) -> None:
        self._observed["server_closed_keep_running"] = keep_running


class _ObservedWorker:
    def __init__(self, *, model: str, max_iterations: int) -> None:
        self.model = model
        self.max_iterations = max_iterations


class _ObservedBenchmark:
    observed: dict[str, object]

    def __init__(self, *, limit: int, worker_factory) -> None:
        self.observed["benchmark_limit"] = limit
        self.worker = worker_factory()


def test_parser_uses_getting_started_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ERGON_LLAMA_CPP_BASE_URL", raising=False)
    monkeypatch.delenv("ERGON_LLAMA_CPP_MODEL", raising=False)
    monkeypatch.delenv("ERGON_MINIF2F_LIMIT", raising=False)
    monkeypatch.delenv("ERGON_MINIF2F_MAX_ITERATIONS", raising=False)
    module = _load_example_module()

    args = module.parse_args([])

    assert args.limit == 3
    assert args.base_url == "http://localhost:8080"
    assert args.model is None
    assert args.model_target is None
    assert args.max_iterations == 12


def test_env_defaults_feed_parser_and_model_target(monkeypatch) -> None:
    monkeypatch.setenv("ERGON_LLAMA_CPP_BASE_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("ERGON_LLAMA_CPP_MODEL", "local-proof-model")
    monkeypatch.setenv("ERGON_MINIF2F_LIMIT", "2")
    monkeypatch.setenv("ERGON_MINIF2F_MAX_ITERATIONS", "5")
    module = _load_example_module()

    args = module.parse_args([])

    assert args.limit == 2
    assert args.base_url == "http://127.0.0.1:9090"
    assert args.model == "local-proof-model"
    assert args.max_iterations == 5
    assert module.model_target_from_args(args) == "llamacpp:http://127.0.0.1:9090#local-proof-model"


def test_parser_accepts_managed_hf_base_model() -> None:
    module = _load_example_module()

    args = module.parse_args(
        [
            "--base-model",
            "unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf",
            "--model-cache-dir",
            "/tmp/ergon-models",
            "--llama-server-bin",
            "/opt/llama-server",
            "--host",
            "127.0.0.1",
            "--port",
            "8123",
            "--startup-timeout",
            "15",
            "--keep-llama-server",
        ]
    )

    assert args.base_model == "unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf"
    assert args.model_cache_dir == "/tmp/ergon-models"
    assert args.llama_server_bin == "/opt/llama-server"
    assert args.host == "127.0.0.1"
    assert args.port == 8123
    assert args.startup_timeout == 15
    assert args.keep_llama_server is True


def test_explicit_model_target_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("ERGON_LLAMA_CPP_MODEL", "model-name-that-should-not-win")
    module = _load_example_module()
    args = module.parse_args(
        [
            "--base-url",
            "http://localhost:8080",
            "--model",
            "local-model",
            "--model-target",
            "openai-compatible:http://model-router:9000#served-model",
        ]
    )

    assert module.model_target_from_args(args) == (
        "openai-compatible:http://model-router:9000#served-model"
    )
    assert module.preflight_base_url_from_args(args) == "http://model-router:9000"


def test_preflight_reports_missing_e2b_key(monkeypatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setattr(env.settings, "e2b_api_key", "")

    with pytest.raises(env.ExampleSetupError, match="E2B_API_KEY"):
        env.preflight_llamacpp_and_e2b(base_url="http://localhost:8080")


def test_preflight_reports_unreachable_llama_cpp(monkeypatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setattr(env.settings, "e2b_api_key", "test-key")

    def fake_urlopen(url: str, timeout: int) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(env.ExampleSetupError, match="llama.cpp server"):
        env.preflight_llamacpp_and_e2b(base_url="http://localhost:8080")


def test_preflight_returns_discovered_model(monkeypatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setattr(env.settings, "e2b_api_key", "test-key")
    calls: list[tuple[str, int]] = []

    def fake_urlopen(url: str, timeout: int) -> _FakeModelsResponse:
        calls.append((url, timeout))
        return _FakeModelsResponse("mini-proof-local")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = env.preflight_llamacpp_and_e2b(base_url="http://localhost:8080/")

    assert result.discovered_model == "mini-proof-local"
    assert calls == [("http://localhost:8080/v1/models", 5)]


def test_model_cache_returns_existing_local_path(tmp_path: Path) -> None:
    model_path = tmp_path / "prover.gguf"
    model_path.write_text("fake model")

    assert model_cache.resolve_base_model(str(model_path)) == model_path.resolve()


def test_model_cache_downloads_huggingface_ref(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cached_file = tmp_path / "hub" / "model.gguf"
    cached_file.parent.mkdir()
    cached_file.write_text("fake model")
    calls: list[tuple[str, str, str]] = []

    def fake_download(*, repo_id: str, filename: str, cache_dir: str) -> str:
        calls.append((repo_id, filename, cache_dir))
        return str(cached_file)

    monkeypatch.setattr(model_cache, "hf_hub_download", fake_download)

    resolved = model_cache.resolve_base_model(
        "unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf",
        cache_dir=tmp_path / "models",
    )

    assert resolved == cached_file
    assert calls == [
        (
            "unsloth/DeepSeek-Prover-V2-7B-GGUF",
            "Q4_K_M.gguf",
            str(tmp_path / "models"),
        )
    ]


def test_model_cache_rejects_missing_local_or_invalid_hf_ref() -> None:
    with pytest.raises(env.ExampleSetupError, match="Hugging Face ref"):
        model_cache.resolve_base_model("/missing/model.gguf")


def test_llamacpp_server_manager_builds_argv_and_discovers_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        returncode = None

        def __init__(self, argv: list[str]) -> None:
            self.argv = argv
            self.terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            return 0

    processes: list[FakeProcess] = []

    def fake_popen(argv, stdout, stderr, text):
        process = FakeProcess(list(argv))
        processes.append(process)
        return process

    def fake_discover(*, base_url: str, timeout_seconds: float) -> str:
        assert base_url == "http://127.0.0.1:8123"
        assert timeout_seconds == 15
        return "mini-proof-local"

    monkeypatch.setattr(llamacpp.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(llamacpp, "discover_llamacpp_model", fake_discover)

    server = llamacpp.start_llama_server(
        base_model="/models/prover.gguf",
        llama_server_bin="llama-server",
        host="127.0.0.1",
        port=8123,
        startup_timeout=15,
    )

    assert processes[0].argv == [
        "llama-server",
        "--model",
        "/models/prover.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "8123",
    ]
    assert server.base_url == "http://127.0.0.1:8123"
    assert server.discovered_model == "mini-proof-local"
    server.close(keep_running=False)
    assert processes[0].terminated is True


@pytest.mark.asyncio
async def test_main_persists_and_launches_minif2f_with_local_worker(monkeypatch, capsys) -> None:
    module = _load_example_module()
    observed: dict[str, object] = {}
    definition_id = UUID("11111111-1111-1111-1111-111111111111")
    run_id = UUID("22222222-2222-2222-2222-222222222222")

    def fake_preflight(*, base_url: str) -> object:
        observed["preflight_base_url"] = base_url
        return object()

    class FakeWorker:
        def __init__(self, *, model: str, max_iterations: int) -> None:
            self.model = model
            self.max_iterations = max_iterations

    def fake_make_worker(*, model: str, max_iterations: int) -> FakeWorker:
        observed["worker_model"] = model
        observed["worker_max_iterations"] = max_iterations
        return FakeWorker(model=model, max_iterations=max_iterations)

    class FakeBenchmark:
        def __init__(self, *, limit: int, worker_factory) -> None:
            observed["benchmark_limit"] = limit
            self.worker = worker_factory()

    class FakeHandle:
        def __init__(self, persisted_definition_id: UUID) -> None:
            self.definition_id = persisted_definition_id

    class FakeRunResult:
        def __init__(self, launched_run_id: UUID) -> None:
            self.run_ids = [launched_run_id]

    def fake_persist_benchmark(benchmark: FakeBenchmark) -> FakeHandle:
        observed["persisted_worker_model"] = benchmark.worker.model
        return FakeHandle(definition_id)

    async def fake_launch_run(persisted_definition_id: UUID) -> FakeRunResult:
        observed["launched_definition_id"] = persisted_definition_id
        return FakeRunResult(run_id)

    monkeypatch.setattr(module, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(module, "MiniF2FBenchmark", FakeBenchmark)
    monkeypatch.setattr(module, "make_minif2f_worker", fake_make_worker)
    monkeypatch.setattr(module, "persist_benchmark", fake_persist_benchmark)
    monkeypatch.setattr(module, "launch_run", fake_launch_run)
    monkeypatch.setenv("ERGON_DASHBOARD_URL", "http://localhost:3000")

    exit_code = await module.async_main(
        [
            "--limit",
            "2",
            "--base-url",
            "http://localhost:8080",
            "--model",
            "local-proof-model",
            "--max-iterations",
            "4",
        ]
    )

    assert exit_code == 0
    assert observed == {
        "preflight_base_url": "http://localhost:8080",
        "benchmark_limit": 2,
        "worker_model": "llamacpp:http://localhost:8080#local-proof-model",
        "worker_max_iterations": 4,
        "persisted_worker_model": "llamacpp:http://localhost:8080#local-proof-model",
        "launched_definition_id": definition_id,
    }
    output = capsys.readouterr().out
    assert str(definition_id) in output
    assert str(run_id) in output
    assert "uv run ergon run status 22222222-2222-2222-2222-222222222222" in output
    assert "http://localhost:3000/run/22222222-2222-2222-2222-222222222222" in output


@pytest.mark.asyncio
async def test_main_resolves_base_model_starts_llamacpp_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_example_module()
    observed: dict[str, object] = {}
    definition_id = UUID("33333333-3333-3333-3333-333333333333")
    run_id = UUID("44444444-4444-4444-4444-444444444444")
    resolved_model = tmp_path / "model.gguf"
    resolved_model.write_text("fake model")

    def fake_resolve(base_model: str, *, cache_dir: str | None) -> Path:
        observed["base_model"] = base_model
        observed["cache_dir"] = cache_dir
        return resolved_model

    def fake_start(**kwargs) -> _ManagedServerStub:
        observed["llama_kwargs"] = kwargs
        return _ManagedServerStub(observed)

    def fake_preflight(*, base_url: str) -> object:
        observed["preflight_base_url"] = base_url
        return object()

    def fake_make_worker(*, model: str, max_iterations: int) -> _ObservedWorker:
        observed["worker_model"] = model
        observed["worker_max_iterations"] = max_iterations
        return _ObservedWorker(model=model, max_iterations=max_iterations)

    class FakeHandle:
        def __init__(self, persisted_definition_id: UUID) -> None:
            self.definition_id = persisted_definition_id

    class FakeRunResult:
        def __init__(self, launched_run_id: UUID) -> None:
            self.run_ids = [launched_run_id]

    def fake_persist_benchmark(benchmark: _ObservedBenchmark) -> FakeHandle:
        observed["persisted_worker_model"] = benchmark.worker.model
        return FakeHandle(definition_id)

    async def fake_launch_run(persisted_definition_id: UUID) -> FakeRunResult:
        observed["launched_definition_id"] = persisted_definition_id
        return FakeRunResult(run_id)

    monkeypatch.setattr(module, "resolve_base_model", fake_resolve)
    monkeypatch.setattr(module, "start_llama_server", fake_start)
    monkeypatch.setattr(module, "preflight_llamacpp_and_e2b", fake_preflight)
    _ObservedBenchmark.observed = observed
    monkeypatch.setattr(module, "MiniF2FBenchmark", _ObservedBenchmark)
    monkeypatch.setattr(module, "make_minif2f_worker", fake_make_worker)
    monkeypatch.setattr(module, "persist_benchmark", fake_persist_benchmark)
    monkeypatch.setattr(module, "launch_run", fake_launch_run)

    exit_code = await module.async_main(
        [
            "--limit",
            "3",
            "--base-model",
            "unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf",
            "--model-cache-dir",
            "/tmp/ergon-models",
            "--llama-server-bin",
            "/opt/llama-server",
            "--host",
            "127.0.0.1",
            "--port",
            "8123",
            "--startup-timeout",
            "15",
            "--keep-llama-server",
        ]
    )

    assert exit_code == 0
    assert observed == {
        "base_model": "unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf",
        "cache_dir": "/tmp/ergon-models",
        "llama_kwargs": {
            "base_model": str(resolved_model),
            "llama_server_bin": "/opt/llama-server",
            "host": "127.0.0.1",
            "port": 8123,
            "startup_timeout": 15,
        },
        "preflight_base_url": "http://127.0.0.1:8123",
        "benchmark_limit": 3,
        "worker_model": "llamacpp:http://127.0.0.1:8123#mini-proof-local",
        "worker_max_iterations": 12,
        "persisted_worker_model": "llamacpp:http://127.0.0.1:8123#mini-proof-local",
        "launched_definition_id": definition_id,
        "server_closed_keep_running": True,
    }
