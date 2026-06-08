"""Internal data containers for the live-Elasticsearch feature.

Pydantic lives only at the HTTP edge (``_schemas``); everything below the route
handlers passes these frozen dataclasses around.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EsConnection:
    """Everything needed to reach one cluster for the life of a session."""

    base_url: str
    username: str
    password: str
    tls_enabled: bool
    ca_cert: str | None = None


@dataclass(frozen=True, slots=True)
class ClusterInfo:
    cluster_name: str
    version: str


@dataclass(frozen=True, slots=True)
class TemplateInfo:
    name: str
    index_patterns: tuple[str, ...]
    has_data_stream: bool


@dataclass(frozen=True, slots=True)
class DataStreamInfo:
    name: str
    template: str | None
    ilm_policy: str | None
    indices_count: int


@dataclass(frozen=True, slots=True)
class IndexInfo:
    name: str
    health: str | None
    docs: int | None
    size: str | None
    ilm_policy: str | None


@dataclass(frozen=True, slots=True)
class ImportResult:
    """A resolved item ready to drop into the existing convert pipeline."""

    index_name: str
    mapping: Mapping[str, Any]
    config_prefill: Mapping[str, Any]
    suggestions: tuple[str, ...]
