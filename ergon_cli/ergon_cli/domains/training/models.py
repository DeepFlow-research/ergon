from typing import Literal

from pydantic import BaseModel, ConfigDict


class TrainingCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["local"]
    ergon_url: str
    benchmark: str
    evaluator: str
    limit: int | None
    definition_id: str | None
    model: str
    device: Literal["cpu", "cuda"]
    vllm_mode: Literal["colocate", "server"] | None
    vllm_server_url: str | None
    vllm_max_model_length: int
    vllm_gpu_memory_utilization: float
    gradient_checkpointing: bool
    num_generations: int
    max_completion_length: int
    learning_rate: float
    per_device_batch_size: int
    gradient_accumulation_steps: int
    num_train_epochs: int
    save_steps: int
    max_steps: int | None
    output_dir: str
    timeout: float
    dataset_size: int
