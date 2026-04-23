"""Device resolution: map TrainingConfig to TRL GRPOConfig kwargs."""

from typing import Required, TypedDict

from ergon_infra.training.config import TrainingConfig


class GRPODeviceKwargs(TypedDict, total=False):
    """GRPOConfig kwargs produced by :func:`resolve_device_mode`.

    ``use_vllm`` is always present; the remaining keys depend on the mode.
    """

    use_vllm: Required[bool]
    use_cpu: bool
    vllm_mode: str
    vllm_server_base_url: str


def resolve_device_mode(config: TrainingConfig) -> GRPODeviceKwargs:
    """Resolve a ``TrainingConfig`` into TRL-compatible GRPOConfig kwargs.

    Returns a :class:`GRPODeviceKwargs` suitable for ``GRPOConfig(**device_kwargs, ...)``.
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
