"""Pydantic request/response models for the live-Elasticsearch endpoints.

These mirror the internal dataclasses in ``_models`` and exist only to give the
HTTP boundary validation and an OpenAPI contract for the frontend.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ._models import DataStreamInfo, ImportResult, IndexInfo, TemplateInfo


class ConnectRequest(BaseModel):
    url: str = Field(..., description="Cluster base URL, e.g. https://es.example:9200")
    username: str
    password: str
    tls_enabled: bool = Field(
        default=True, description="For https: verify the server certificate. Ignored for http."
    )
    ca_cert: str | None = Field(default=None, description="Optional CA certificate PEM string.")


class ConnectResponse(BaseModel):
    session_id: str
    cluster_name: str
    version: str


class DisconnectRequest(BaseModel):
    session_id: str


class TemplateItem(BaseModel):
    name: str
    index_patterns: list[str]
    has_data_stream: bool

    @classmethod
    def from_info(cls, info: TemplateInfo) -> TemplateItem:
        return cls(
            name=info.name,
            index_patterns=list(info.index_patterns),
            has_data_stream=info.has_data_stream,
        )


class DataStreamItem(BaseModel):
    name: str
    template: str | None
    ilm_policy: str | None
    indices_count: int

    @classmethod
    def from_info(cls, info: DataStreamInfo) -> DataStreamItem:
        return cls(
            name=info.name,
            template=info.template,
            ilm_policy=info.ilm_policy,
            indices_count=info.indices_count,
        )


class IndexItem(BaseModel):
    name: str
    health: str | None
    docs: int | None
    size: str | None
    ilm_policy: str | None

    @classmethod
    def from_info(cls, info: IndexInfo) -> IndexItem:
        return cls(
            name=info.name,
            health=info.health,
            docs=info.docs,
            size=info.size,
            ilm_policy=info.ilm_policy,
        )


class ImportResponse(BaseModel):
    index_name: str
    mapping: dict[str, Any]
    config_prefill: dict[str, Any]
    suggestions: list[str]

    @classmethod
    def from_result(cls, result: ImportResult) -> ImportResponse:
        return cls(
            index_name=result.index_name,
            mapping=dict(result.mapping),
            config_prefill=dict(result.config_prefill),
            suggestions=list(result.suggestions),
        )
