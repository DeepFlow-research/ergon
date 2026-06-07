from argparse import Namespace

import ergon_cli.domains.training.commands as training_commands


def _train_args(**overrides: object) -> Namespace:
    data = {
        "train_action": "local",
        "ergon_url": "http://localhost:9000/api",
        "environment": "env",
        "evaluator": "stub-rubric",
        "limit": None,
        "experiment_id": None,
        "model": "Qwen/Qwen2.5-1.5B",
        "device": "cuda",
        "vllm_mode": "server",
        "vllm_server_url": None,
        "vllm_max_model_length": 4096,
        "vllm_gpu_memory_utilization": 0.3,
        "no_gradient_checkpointing": False,
        "num_generations": 4,
        "max_completion_length": 2048,
        "learning_rate": 1e-5,
        "per_device_batch_size": 1,
        "gradient_accumulation_steps": 4,
        "num_train_epochs": 1,
        "save_steps": 50,
        "max_steps": None,
        "output_dir": ".ergon/training/checkpoints",
        "timeout": 300.0,
        "dataset_size": 100,
    }
    data.update(overrides)
    return Namespace(**data)


def test_train_local_builds_typed_command_before_optional_dependency_check(monkeypatch):
    captured = {}

    def fake_run_training(command):
        captured["command"] = command
        return 0

    monkeypatch.setattr(training_commands, "run_training", fake_run_training)

    rc = training_commands.handle_train(
        _train_args(device="cpu", vllm_mode="server", experiment_id="experiment-1")
    )

    assert rc == 0
    assert captured["command"].experiment_id == "experiment-1"
    assert captured["command"].device == "cpu"
    assert captured["command"].vllm_mode is None
