from uuid import uuid4

from pydantic import BaseModel

from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask


class ExampleTaskPayload(BaseModel):
    value: int


def test_definition_task_payload_accessor_returns_pydantic_model() -> None:
    task = ExperimentDefinitionTask(
        id=uuid4(),
        experiment_definition_id=uuid4(),
        instance_id=uuid4(),
        task_slug="example",
        description="Example task",
        task_payload_json={"value": 42},
    )

    payload = task.task_payload_as(ExampleTaskPayload)

    assert payload == ExampleTaskPayload(value=42)
    assert not isinstance(payload, dict)
    assert not hasattr(task, "task_payload")
