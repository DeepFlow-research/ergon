from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ListExperimentsCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    limit: int = 50


class ShowExperimentCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    experiment_id: UUID


class ExperimentSamplesCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    experiment_id: UUID


class ExperimentSamplerInvocationsCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    experiment_id: UUID


class ExperimentEnvironmentCliState(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment_id: UUID
    environment_name: str
    source_mode: str
    sample_count: int
    selected_count: int


class ExperimentSampleCliState(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: UUID
    environment_name: str
    sample_key: str
    status: str


class SamplerInvocationCliState(BaseModel):
    model_config = ConfigDict(frozen=True)

    sampler_invocation_id: UUID
    sampler_name: str
    requested_k: int
    candidate_pool_size: int
    selected_count: int


class ExperimentCliState(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: UUID
    name: str
    environments: tuple[ExperimentEnvironmentCliState, ...]
    sample_count: int
    sampler_invocation_count: int
    samples: tuple[ExperimentSampleCliState, ...] = ()


class ExperimentListCliResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiments: tuple[ExperimentCliState, ...]


class ExperimentSamplesCliResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    samples: tuple[ExperimentSampleCliState, ...]


class ExperimentSamplerInvocationsCliResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocations: tuple[SamplerInvocationCliState, ...]
