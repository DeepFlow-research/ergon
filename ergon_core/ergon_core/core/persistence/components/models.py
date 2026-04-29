"""Persistent component catalog shared across CLI/API/Inngest processes."""

from datetime import datetime
from uuid import UUID, uuid4

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)
COMPONENT_KINDS = {"worker", "benchmark", "evaluator", "sandbox_manager", "model_backend"}


class ComponentCatalogEntry(SQLModel, table=True):
    __tablename__ = "component_catalog"
    __table_args__ = (UniqueConstraint("kind", "slug", name="uq_component_catalog_kind_slug"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True)
    slug: str = Field(index=True)
    module: str
    qualname: str
    package: str | None = Field(default=None, index=True)
    version: str | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        self._validate_invariants()

    def parsed_metadata(self) -> JsonObject:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_entry(self) -> "ComponentCatalogEntry":
        self._validate_invariants()
        return self

    def _validate_invariants(self) -> None:
        if self.kind not in COMPONENT_KINDS:
            allowed = ", ".join(sorted(COMPONENT_KINDS))
            raise ValueError(f"kind must be one of: {allowed}")
        if not self.slug:
            raise ValueError("slug must be non-empty")
        if not self.module:
            raise ValueError("module must be non-empty")
        if not self.qualname:
            raise ValueError("qualname must be non-empty")
        self.__class__._parse_metadata(self.metadata_json)
