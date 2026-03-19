"""Pydantic schemas for setup and onboarding services."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServiceCheck(BaseModel):
    """Readiness status for a local or remote dependency."""

    name: str
    ok: bool
    detail: str


class EnvVarCheck(BaseModel):
    """Status for a single environment variable."""

    name: str
    present: bool
    source: str


class BenchmarkStatus(BaseModel):
    """Preparation status for a benchmark."""

    benchmark: str
    prepared: bool
    detail: str
    location: str | None = None


class BenchmarkPrepareResult(BaseModel):
    """Result for a benchmark preparation action."""

    benchmark: str
    prepared: bool
    detail: str
    location: str | None = None


class BenchmarkSeedResult(BaseModel):
    """Result for a benchmark seeding action."""

    benchmark: str
    database_target: str
    created_experiment_ids: list[str] = Field(default_factory=list)
    detail: str


class DoctorReport(BaseModel):
    """Full readiness report for `magym doctor`."""

    env_checks: list[EnvVarCheck] = Field(default_factory=list)
    service_checks: list[ServiceCheck] = Field(default_factory=list)
    database_checks: list[ServiceCheck] = Field(default_factory=list)
    benchmark_checks: list[BenchmarkStatus] = Field(default_factory=list)
