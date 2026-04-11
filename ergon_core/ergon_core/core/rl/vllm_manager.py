"""vLLM process lifecycle manager.

Manages a standalone vLLM OpenAI-compatible server as a subprocess.
Used by the Ergon API to serve model weights for workers and to
restart with updated checkpoints after training steps.

Targets full-weight RFT: restart() kills the process and starts a new
one with the updated checkpoint path (no hot-reload).
"""

import logging
import signal
import subprocess
import time

import httpx

logger = logging.getLogger(__name__)


class VLLMManager:
    """Manage a vLLM server subprocess."""

    def __init__(
        self,
        model: str,
        host: str = "0.0.0.0",
        port: int = 8000,
        max_model_len: int = 4096,
        gpu_memory_utilization: float = 0.3,
        extra_args: list[str] | None = None,
    ) -> None:
        self._model = model
        self._host = host
        self._port = port
        self._max_model_len = max_model_len
        self._gpu_memory_utilization = gpu_memory_utilization
        self._extra_args = extra_args or []
        self._process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, timeout_s: float = 120.0) -> None:
        """Start the vLLM server and block until healthy."""
        if self.is_running:
            logger.warning("vLLM already running (pid=%s)", self._process.pid)
            return

        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", self._model,
            "--host", self._host,
            "--port", str(self._port),
            "--max-model-len", str(self._max_model_len),
            "--gpu-memory-utilization", str(self._gpu_memory_utilization),
            *self._extra_args,
        ]
        logger.info("Starting vLLM: %s", " ".join(cmd))
        self._process = subprocess.Popen(cmd)
        self._wait_healthy(timeout_s)
        logger.info("vLLM healthy (pid=%s, model=%s)", self._process.pid, self._model)

    def stop(self, timeout_s: float = 10.0) -> None:
        """Stop the vLLM server."""
        if not self.is_running:
            return
        assert self._process is not None
        logger.info("Stopping vLLM (pid=%s)", self._process.pid)
        self._process.send_signal(signal.SIGTERM)
        try:
            self._process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            logger.warning("vLLM didn't exit after SIGTERM, sending SIGKILL")
            self._process.kill()
            self._process.wait()
        self._process = None

    def restart(self, checkpoint_path: str, timeout_s: float = 120.0) -> None:
        """Restart vLLM with a new model checkpoint.

        For full-weight RFT: stop the current process, start a new one
        pointing at the checkpoint directory.
        """
        logger.info("Restarting vLLM with checkpoint: %s", checkpoint_path)
        self.stop()
        self._model = checkpoint_path
        self.start(timeout_s)

    def health(self) -> bool:
        """Check if the server is responding."""
        try:
            resp = httpx.get(f"http://localhost:{self._port}/health", timeout=5.0)
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def _wait_healthy(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.health():
                return
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"vLLM process exited with code {self._process.returncode}"
                )
            time.sleep(2.0)
        raise TimeoutError(f"vLLM server didn't become healthy within {timeout_s}s")
