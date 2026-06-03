"""Pydantic models for the HTTP boundary (validation + OpenAPI schema).

These exist only at the edge so the future frontend gets a typed contract;
internal logic uses the dataclasses in ``mapping``/``ddl``.
"""

from typing import Any

from pydantic import BaseModel, Field

from .ddl import DdlArtifacts


class ConvertRequest(BaseModel):
    index_name: str = Field(..., description="ClickHouse table name to generate.")
    mapping: dict[str, Any] = Field(
        ..., description="Raw Elasticsearch _mapping JSON (full response or a bare block)."
    )
    config: dict[str, Any] | None = Field(
        default=None, description="Optional per-index conversion config."
    )


class ConvertResponse(BaseModel):
    table_name: str
    ddl: str = ""
    warnings: list[str] = []
    suggestions: list[str] = []
    error: str | None = None

    @classmethod
    def from_artifacts(cls, artifacts: DdlArtifacts) -> "ConvertResponse":
        return cls(
            table_name=artifacts.table_name,
            ddl=artifacts.ddl,
            warnings=list(artifacts.warnings),
            suggestions=list(artifacts.suggestions),
        )

    @classmethod
    def from_error(cls, table_name: str, error: str) -> "ConvertResponse":
        return cls(table_name=table_name, error=error)
