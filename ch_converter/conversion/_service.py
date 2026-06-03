"""Conversion orchestrator — the single code path shared by the API and CLI."""

from collections.abc import Mapping
from typing import Any

from ..ddl import DdlArtifacts, IndexConfig, generate_ddl, load_index_config
from ..mapping import parse_mapping
from ..sampling import SampleProfile


def convert_index(
    index_name: str,
    mapping_raw: dict[str, Any],
    config: IndexConfig | Mapping[str, Any] | None = None,
    profile: SampleProfile | None = None,
) -> DdlArtifacts:
    """Convert one ES index mapping into ClickHouse DDL plus advisories."""
    model = parse_mapping(mapping_raw)
    index_config = config if isinstance(config, IndexConfig) else load_index_config(config)
    return generate_ddl(index_name, model, index_config, profile)
