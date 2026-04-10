"""Device resolution: map TrainingConfig to TRL GRPOConfig kwargs."""

from arcane_infra.training.config import TrainingConfig


def resolve_device_mode(config: TrainingConfig) -> dict:
    """Resolve a ``TrainingConfig`` into TRL-compatible GRPOConfig kwargs.

    Returns a dict with keys consumed by ``GRPOConfig``:
    ``use_vllm``, ``vllm_mode``, ``vllm_server_base_url``, ``no_cuda``.
    """
    if config.device == "cpu":
        return {
            "use_vllm": False,
            "use_cpu": True,
        }

    if config.vllm_mode == "colocate":
        return {
            "use_vllm": True,
            "vllm_mode": "colocate",
        }

    if config.vllm_mode == "server":
        if not config.vllm_server_url:
            raise ValueError("--vllm-server-url is required when --vllm-mode=server")
        return {
            "use_vllm": True,
            "vllm_mode": "server",
            "vllm_server_base_url": config.vllm_server_url,
        }

    raise ValueError(f"Unknown vllm_mode: {config.vllm_mode}")
