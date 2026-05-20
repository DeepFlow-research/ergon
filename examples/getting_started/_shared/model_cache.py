"""Resolve local and Hugging Face GGUF model references for examples."""

from pathlib import Path

from huggingface_hub import hf_hub_download
from huggingface_hub.utils import HfHubHTTPError, HFValidationError, LocalEntryNotFoundError

from getting_started._shared.env import ExampleSetupError, env_optional_str

DEFAULT_MODEL_CACHE_DIR = Path.home() / ".cache" / "ergon" / "examples" / "models"


def resolve_base_model(value: str, *, cache_dir: Path | str | None = None) -> Path:
    """Return a local GGUF path for either a filesystem path or ``repo:filename``."""
    local_path = Path(value).expanduser()
    if local_path.is_file():
        return local_path.resolve()

    repo_id, filename = _parse_hf_model_ref(value)
    target_cache_dir = _model_cache_dir(cache_dir)
    try:
        resolved = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            cache_dir=str(target_cache_dir),
        )
    except (
        HfHubHTTPError,
        HFValidationError,
        LocalEntryNotFoundError,
        OSError,
    ) as exc:
        raise ExampleSetupError(
            f"Could not download base model {value!r} from Hugging Face. "
            "Use '<repo-id>:<filename.gguf>' or pass an existing local GGUF path."
        ) from exc
    return Path(resolved)


def _model_cache_dir(cache_dir: Path | str | None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir).expanduser()

    configured = env_optional_str("ERGON_EXAMPLE_MODEL_CACHE_DIR")
    if configured is not None:
        return Path(configured).expanduser()

    return DEFAULT_MODEL_CACHE_DIR


def _parse_hf_model_ref(value: str) -> tuple[str, str]:
    repo_id, separator, filename = value.partition(":")
    if not separator or not repo_id or not filename:
        raise ExampleSetupError(
            f"Base model {value!r} was not found locally. "
            "Pass an existing local GGUF path or a Hugging Face ref like "
            "'unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf'."
        )
    if not filename.endswith(".gguf"):
        raise ExampleSetupError(f"Base model file {filename!r} must be a GGUF file for llama.cpp.")
    return repo_id, filename
