"""Tests for the MiniF2F llama.cpp getting-started example."""

import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from types import SimpleNamespace
from uuid import UUID

import pytest

from ergon_core.api import Environment, Evaluator, ExperimentSubmitResult, Sample, Sandbox, Worker
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.test_support.task_factory import task_with_id
from getting_started._shared import llamacpp
from getting_started._shared import model_cache
from getting_started._shared import env

_EXAMPLE_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "getting_started"
    / "01_minif2f_local_llamacpp"
    / "submit.py"
)


def _load_example_module():
    spec = importlib.util.spec_from_file_location("minif2f_local_llamacpp_submit", _EXAMPLE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_uses_packaged_imports_without_repo_root_sys_path_hack() -> None:
    source = _EXAMPLE_PATH.read_text()

    assert "sys.path.insert" not in source
    assert "Path(__file__).resolve().parents" not in source
    assert "MiniF2FBenchmark" not in source
    assert "persist_benchmark" not in source
    assert "launch_run" not in source
    assert "from ergon_core.api import Environment, Experiment, RandomSampler" in source
    assert "from ergon_builtins.benchmarks.minif2f.dataset import load_minif2f_rows" in source
    assert "from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample" in source
    assert "MiniF2FEnvironment" not in source
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


class _ObservedWorker(Worker):
    type_slug = "observed-worker"

    max_iterations: int | None = None
    system_prompt: str | None = None
    toolkit: object | None = None

    async def execute(self, task, *, context):
        del task, context
        if False:
            yield WorkerOutput(output="ok")


class _ObservedSandbox(Sandbox):
    async def provision(self) -> None:
        return None

    async def _bind_runtime(self, sandbox_id: str) -> None:
        del sandbox_id
        return None


class _ObservedEvaluator(Evaluator):
    type_slug = "observed-evaluator"

    def criteria_for(self, task):
        del task
        return []

    def aggregate_task(self, task, criterion_results):
        del task, criterion_results
        raise NotImplementedError


class _ObservedComponent:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


class _ObservedEnvironment(Environment):
    def iter_samples(self):
        return iter(())


def _fake_minif2f_rows(*, split: str, limit: int) -> list[SimpleNamespace]:
    return [SimpleNamespace(name=f"sample-{index}", split=split) for index in range(limit)]


def _fake_minif2f_sample(
    row,
    *,
    environment_name: str,
    worker,
    evaluators,
    sandbox,
    **kwargs,
) -> Sample:
    del kwargs
    return Sample.from_tasks(
        name=f"{environment_name}:{row.name}",
        sample_key=row.name,
        environment_name=environment_name,
        tasks=[
            task_with_id(
                UUID("00000000-0000-0000-0000-000000000099"),
                task_slug="solve",
                instance_key=row.name,
                description=f"Solve {row.name}",
                worker=worker,
                evaluators=tuple(evaluators),
                sandbox=sandbox,
            )
        ],
    )


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
async def test_main_submits_minif2f_with_local_worker(monkeypatch, capsys) -> None:
    module = _load_example_module()
    observed: dict[str, object] = {}
    sample_id = UUID("22222222-2222-2222-2222-222222222222")
    experiment_id = UUID("11111111-1111-1111-1111-111111111111")

    def fake_preflight(*, base_url: str) -> object:
        observed["preflight_base_url"] = base_url
        return object()

    class CapturingEnvironment:
        @classmethod
        def from_records(cls, **kwargs) -> _ObservedEnvironment:
            observed["environment_kwargs"] = kwargs
            observed["samples"] = [kwargs["make_sample"](row) for row in kwargs["records"]]
            return _ObservedEnvironment(name=kwargs["name"])

    class FakeService:
        async def __call__(
            self,
            *,
            experiment,
            k: int,
            sampler,
            candidate_pool_size,
            policy_version,
            session,
            event_bus,
        ):
            del session, event_bus
            observed["experiment_name"] = experiment.name
            observed["k"] = k
            observed["sampler_name"] = sampler.name
            observed["candidate_pool_size"] = candidate_pool_size
            observed["policy_version"] = policy_version
            return ExperimentSubmitResult(
                experiment_id=experiment_id,
                requested_k=k,
                candidate_pool_size=k,
                selected_count=1,
                sample_ids=[sample_id],
            )

    monkeypatch.setattr(module, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(module, "Environment", CapturingEnvironment)
    monkeypatch.setattr(module, "ReActWorker", _ObservedWorker)
    monkeypatch.setattr(module, "MiniF2FToolkit", _ObservedComponent)
    monkeypatch.setattr(module, "MiniF2FRubric", _ObservedEvaluator)
    monkeypatch.setattr(module, "LeanSandbox", _ObservedSandbox)
    monkeypatch.setattr(module, "load_minif2f_rows", _fake_minif2f_rows)
    monkeypatch.setattr(module, "make_minif2f_sample", _fake_minif2f_sample)
    monkeypatch.setattr(module, "prepare_experiment_runtime", lambda: None)
    monkeypatch.setattr(
        "ergon_core.core.application.experiments.submission.submit_experiment",
        FakeService(),
    )
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
    assert observed["preflight_base_url"] == "http://localhost:8080"
    environment_kwargs = observed["environment_kwargs"]
    assert environment_kwargs["name"] == "mini-validation"
    assert len(observed["samples"]) == 2
    worker = observed["samples"][0].tasks[0].worker
    assert isinstance(worker, _ObservedWorker)
    assert worker.model == "llamacpp:http://localhost:8080#local-proof-model"
    assert worker.max_iterations == 4
    assert len(observed["samples"][0].tasks[0].evaluators) == 1
    assert observed["experiment_name"] == "minif2f-local-llamacpp"
    assert observed["k"] == 2
    assert observed["sampler_name"] == "random"
    assert observed["candidate_pool_size"] is None
    assert observed["policy_version"] is None
    output = capsys.readouterr().out
    assert str(experiment_id) in output
    assert str(sample_id) in output
    assert "Definition id" not in output
    assert "uv run ergon sample status 22222222-2222-2222-2222-222222222222" in output
    assert "http://localhost:3000/samples/22222222-2222-2222-2222-222222222222" in output


@pytest.mark.asyncio
async def test_main_resolves_base_model_starts_llamacpp_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_example_module()
    observed: dict[str, object] = {}
    experiment_id = UUID("33333333-3333-3333-3333-333333333333")
    sample_id = UUID("44444444-4444-4444-4444-444444444444")
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

    class CapturingEnvironment:
        @classmethod
        def from_records(cls, **kwargs) -> _ObservedEnvironment:
            observed["environment_kwargs"] = kwargs
            observed["samples"] = [kwargs["make_sample"](row) for row in kwargs["records"]]
            return _ObservedEnvironment(name=kwargs["name"])

    class FakeService:
        async def __call__(
            self,
            *,
            experiment,
            k: int,
            sampler,
            candidate_pool_size,
            policy_version,
            session,
            event_bus,
        ):
            del session, event_bus
            observed["experiment_name"] = experiment.name
            observed["k"] = k
            observed["sampler_name"] = sampler.name
            observed["candidate_pool_size"] = candidate_pool_size
            observed["policy_version"] = policy_version
            return ExperimentSubmitResult(
                experiment_id=experiment_id,
                requested_k=k,
                candidate_pool_size=k,
                selected_count=1,
                sample_ids=[sample_id],
            )

    monkeypatch.setattr(module, "resolve_base_model", fake_resolve)
    monkeypatch.setattr(module, "start_llama_server", fake_start)
    monkeypatch.setattr(module, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(module, "Environment", CapturingEnvironment)
    monkeypatch.setattr(module, "ReActWorker", _ObservedWorker)
    monkeypatch.setattr(module, "MiniF2FToolkit", _ObservedComponent)
    monkeypatch.setattr(module, "MiniF2FRubric", _ObservedEvaluator)
    monkeypatch.setattr(module, "LeanSandbox", _ObservedSandbox)
    monkeypatch.setattr(module, "load_minif2f_rows", _fake_minif2f_rows)
    monkeypatch.setattr(module, "make_minif2f_sample", _fake_minif2f_sample)
    monkeypatch.setattr(module, "prepare_experiment_runtime", lambda: None)
    monkeypatch.setattr(
        "ergon_core.core.application.experiments.submission.submit_experiment",
        FakeService(),
    )

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
        "environment_kwargs": {
            "name": "mini-validation",
            "records": observed["environment_kwargs"]["records"],
            "make_sample": observed["environment_kwargs"]["make_sample"],
        },
        "samples": observed["samples"],
        "experiment_name": "minif2f-local-llamacpp",
        "k": 3,
        "sampler_name": "random",
        "candidate_pool_size": None,
        "policy_version": None,
        "server_closed_keep_running": True,
    }
    worker = observed["samples"][0].tasks[0].worker
    assert isinstance(worker, _ObservedWorker)
    assert worker.model == "llamacpp:http://127.0.0.1:8123#mini-proof-local"
    assert worker.max_iterations == 12
