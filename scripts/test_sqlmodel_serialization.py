"""Test SQLModel serialization with model_dump(mode='json')."""

import json
from datetime import datetime
from uuid import uuid4

from h_arcane.db.models import Run, RunStatus, Experiment, Resource
from sqlmodel import SQLModel
from h_arcane.schemas.base import BenchmarkName
from h_arcane.config.evaluation_config import evaluation_config


def test_run_serialization():
    """Test Run model serialization."""
    print("=" * 60)
    print("Testing Run model serialization")
    print("=" * 60)

    # Create a test Run object
    run = Run(
        id=uuid4(),
        experiment_id=uuid4(),
        worker_model=evaluation_config.llm_stakeholder.model,
        max_questions=10,
        status=RunStatus.EXECUTING,
        created_at=datetime.utcnow(),
        started_at=datetime.utcnow(),
        output_resource_ids=["resource-1", "resource-2"],
        final_score=85.5,
        normalized_score=0.85,
        questions_asked=3,
    )

    print(f"\nRun object: {run}")
    print(f"Run type: {type(run)}")
    print(f"Is SQLModel: {isinstance(run, SQLModel)}")

    # Test model_dump(mode='json')
    try:
        dumped = run.model_dump(mode="json")
        print("\n✅ model_dump(mode='json') succeeded")
        print(f"Type: {type(dumped)}")
        print(f"Keys: {list(dumped.keys())}")

        # Test JSON serialization
        json_str = json.dumps(dumped)
        print("\n✅ JSON serialization succeeded")
        print(f"JSON length: {len(json_str)} chars")

        # Test deserialization
        loaded = json.loads(json_str)
        print("\n✅ JSON deserialization succeeded")
        print(f"Loaded type: {type(loaded)}")

        # Test recreating from dict
        run_recreated = Run(**loaded)
        print("\n✅ Recreating Run from dict succeeded")
        print(f"Recreated Run ID: {run_recreated.id}")
        print(f"Recreated Run status: {run_recreated.status}")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_experiment_serialization():
    """Test Experiment model serialization."""
    print("\n" + "=" * 60)
    print("Testing Experiment model serialization")
    print("=" * 60)

    # Create a test Experiment object

    experiment = Experiment(
        id=uuid4(),
        benchmark_name=BenchmarkName.GDPEVAL,
        task_id="test-task-123",
        task_description="Test task description",
        ground_truth_rubric={"stages": [{"criteria": []}]},
        benchmark_specific_data={},
        category="test",
        created_at=datetime.utcnow(),
    )

    print(f"\nExperiment object: {experiment}")

    try:
        dumped = experiment.model_dump(mode="json")
        print("\n✅ model_dump(mode='json') succeeded")

        json_str = json.dumps(dumped)
        print("✅ JSON serialization succeeded")

        loaded = json.loads(json_str)
        experiment_recreated = Experiment(**loaded)
        print("✅ Recreating Experiment from dict succeeded")
        print(f"Recreated Experiment ID: {experiment_recreated.id}")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_resource_serialization():
    """Test Resource model serialization."""
    print("\n" + "=" * 60)
    print("Testing Resource model serialization")
    print("=" * 60)

    # Create a test Resource object
    resource = Resource(
        id=uuid4(),
        run_id=uuid4(),
        name="test.pdf",
        mime_type="application/pdf",
        file_path="/path/to/test.pdf",
        size_bytes=1024,
    )

    print(f"\nResource object: {resource}")

    try:
        dumped = resource.model_dump(mode="json")
        print("\n✅ model_dump(mode='json') succeeded")

        json_str = json.dumps(dumped)
        print("✅ JSON serialization succeeded")

        loaded = json.loads(json_str)
        resource_recreated = Resource(**loaded)
        print("✅ Recreating Resource from dict succeeded")
        print(f"Recreated Resource name: {resource_recreated.name}")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_list_serialization():
    """Test serializing lists of models."""
    print("\n" + "=" * 60)
    print("Testing list of models serialization")
    print("=" * 60)

    resources = [
        Resource(
            id=uuid4(),
            run_id=uuid4(),
            name=f"file_{i}.pdf",
            mime_type="application/pdf",
            file_path=f"/path/to/file_{i}.pdf",
            size_bytes=1024 * i,
        )
        for i in range(3)
    ]

    print(f"\nCreated {len(resources)} Resource objects")

    try:
        dumped = [r.model_dump(mode="json") for r in resources]
        print("✅ model_dump(mode='json') on list succeeded")

        json_str = json.dumps(dumped)
        print("✅ JSON serialization succeeded")
        print(f"JSON length: {len(json_str)} chars")

        loaded = json.loads(json_str)
        resources_recreated = [Resource(**r_dict) for r_dict in loaded]
        print("✅ Recreating list from JSON succeeded")
        print(f"Recreated {len(resources_recreated)} resources")

        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Testing SQLModel serialization with model_dump(mode='json')\n")

    results = []
    results.append(("Run", test_run_serialization()))
    results.append(("Experiment", test_experiment_serialization()))
    results.append(("Resource", test_resource_serialization()))
    results.append(("List of Resources", test_list_serialization()))

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{name}: {status}")
