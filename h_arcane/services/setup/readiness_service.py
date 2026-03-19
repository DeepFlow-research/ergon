"""Readiness checks for the magym CLI."""

from __future__ import annotations

import os

from huggingface_hub import HfApi
from sqlmodel import create_engine

from h_arcane.core.settings import settings
from h_arcane.services.setup.common import (
    DEFAULT_RESEARCHRUBRICS_DATASET,
    MINIF2F_REQUIRED_FILES,
    parse_env_file,
)
from h_arcane.services.setup.compose_service import ComposeService
from h_arcane.services.setup.schemas import BenchmarkStatus, DoctorReport, EnvVarCheck, ServiceCheck


class ReadinessService:
    """Collect readiness information for local setup commands."""

    def __init__(self):
        self._compose = ComposeService()

    def build_report(self, researchrubrics_dataset_name: str | None = None) -> DoctorReport:
        env_values = parse_env_file()
        dataset_name = researchrubrics_dataset_name or DEFAULT_RESEARCHRUBRICS_DATASET

        return DoctorReport(
            env_checks=self._build_env_checks(env_values),
            service_checks=self._build_service_checks(),
            database_checks=self._build_database_checks(),
            benchmark_checks=[
                self._minif2f_status(),
                self._researchrubrics_status(dataset_name, env_values.get("HF_TOKEN")),
            ],
        )

    def _build_env_checks(self, env_values: dict[str, str]) -> list[EnvVarCheck]:
        return [
            self._env_check("OPENAI_API_KEY", env_values),
            self._env_check("E2B_API_KEY", env_values),
            self._env_check("EXA_API_KEY", env_values),
            self._env_check("HF_TOKEN", env_values),
        ]

    def _env_check(self, name: str, env_values: dict[str, str]) -> EnvVarCheck:
        direct_value = os.getenv(name)
        env_file_value = env_values.get(name)

        if direct_value:
            return EnvVarCheck(name=name, present=True, source="environment")
        if env_file_value:
            return EnvVarCheck(name=name, present=True, source=".env")
        return EnvVarCheck(name=name, present=False, source="missing")

    def _build_service_checks(self) -> list[ServiceCheck]:
        running = self._compose.running_services()
        checks: list[ServiceCheck] = []
        for name in ("postgres", "api", "inngest-dev", "dashboard"):
            checks.append(
                ServiceCheck(
                    name=name,
                    ok=name in running,
                    detail="running" if name in running else "not running",
                )
            )
        return checks

    def _build_database_checks(self) -> list[ServiceCheck]:
        return [
            self._database_check("main", settings.get_database_url("main")),
            self._database_check("test", settings.get_database_url("test")),
        ]

    def _database_check(self, name: str, database_url: str) -> ServiceCheck:
        try:
            engine = create_engine(database_url, pool_pre_ping=True)
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return ServiceCheck(name=f"database:{name}", ok=True, detail="reachable")
        except Exception as exc:
            return ServiceCheck(name=f"database:{name}", ok=False, detail=str(exc))

    def _minif2f_status(self) -> BenchmarkStatus:
        minif2f_dir = settings.data_dir / "raw" / "minif2f"
        missing = [str(minif2f_dir / rel_path) for rel_path in MINIF2F_REQUIRED_FILES if not (minif2f_dir / rel_path).exists()]
        if missing:
            return BenchmarkStatus(
                benchmark="minif2f",
                prepared=False,
                detail=f"missing files: {', '.join(missing)}",
                location=str(minif2f_dir),
            )
        return BenchmarkStatus(
            benchmark="minif2f",
            prepared=True,
            detail="repository is available locally",
            location=str(minif2f_dir),
        )

    def _researchrubrics_status(
        self,
        dataset_name: str,
        hf_token: str | None,
    ) -> BenchmarkStatus:
        try:
            HfApi(token=hf_token or None).dataset_info(dataset_name)
            return BenchmarkStatus(
                benchmark="researchrubrics",
                prepared=True,
                detail=f"dataset reachable: {dataset_name}",
                location=dataset_name,
            )
        except Exception as exc:
            return BenchmarkStatus(
                benchmark="researchrubrics",
                prepared=False,
                detail=f"dataset unavailable: {exc}",
                location=dataset_name,
            )
