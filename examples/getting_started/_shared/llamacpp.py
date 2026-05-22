"""llama.cpp process helpers for getting-started examples."""

import subprocess

from getting_started._shared.env import ExampleSetupError, discover_llamacpp_model


class ManagedLlamaServer:
    def __init__(
        self,
        *,
        process: subprocess.Popen[str],
        base_url: str,
        discovered_model: str,
    ) -> None:
        self._process = process
        self.base_url = base_url
        self.discovered_model = discovered_model

    def close(self, *, keep_running: bool) -> None:
        if keep_running or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=10)


def start_llama_server(
    *,
    base_model: str,
    llama_server_bin: str,
    host: str,
    port: int,
    startup_timeout: int,
) -> ManagedLlamaServer:
    argv = [
        llama_server_bin,
        "--model",
        base_model,
        "--host",
        host,
        "--port",
        str(port),
    ]
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise ExampleSetupError(
            f"Could not start llama.cpp with command: {_display(argv)}. "
            f"OS error: {exc}. Install llama.cpp's server binary or pass "
            "--llama-server-bin /path/to/llama-server."
        ) from exc

    base_url = f"http://{host}:{port}"
    try:
        discovered_model = discover_llamacpp_model(
            base_url=base_url,
            timeout_seconds=startup_timeout,
        )
    except ExampleSetupError:
        _terminate_started_process(process)
        raise
    return ManagedLlamaServer(
        process=process,
        base_url=base_url,
        discovered_model=discovered_model,
    )


def _terminate_started_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _display(argv: list[str]) -> str:
    return " ".join(argv)
