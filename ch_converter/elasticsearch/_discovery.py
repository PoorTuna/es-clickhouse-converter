"""List browsable items on a cluster and resolve a chosen item's mapping.

The three tabs (index templates, data streams, indices) each list lightweight
metadata; ``import_item`` does the heavier per-item resolution (effective
mapping + linked ILM policy) only when the user picks something.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from ._client import EsClient
from ._ilm import translate_ilm
from ._models import DataStreamInfo, ImportResult, IndexInfo, TemplateInfo

ItemKind = Literal["template", "datastream", "index"]


async def list_templates(client: EsClient) -> list[TemplateInfo]:
    payload = await client.get_json("/_index_template")
    items = []
    for entry in payload.get("index_templates", []):
        body = entry.get("index_template", {})
        items.append(
            TemplateInfo(
                name=entry.get("name", ""),
                index_patterns=tuple(body.get("index_patterns", [])),
                has_data_stream="data_stream" in body,
            )
        )
    return items


async def list_data_streams(client: EsClient) -> list[DataStreamInfo]:
    payload = await client.get_json("/_data_stream")
    return [
        DataStreamInfo(
            name=entry.get("name", ""),
            template=entry.get("template"),
            ilm_policy=entry.get("ilm_policy"),
            indices_count=len(entry.get("indices", [])),
        )
        for entry in payload.get("data_streams", [])
    ]


async def list_indices(client: EsClient, include_system: bool) -> list[IndexInfo]:
    params = {"format": "json", "h": "index,health,docs.count,store.size"}
    rows = await client.get_json("/_cat/indices", params=params)
    items = []
    for row in rows:
        name = row.get("index", "")
        if not include_system and name.startswith("."):
            continue
        items.append(
            IndexInfo(
                name=name,
                health=row.get("health"),
                docs=_as_int(row.get("docs.count")),
                size=row.get("store.size"),
                ilm_policy=None,  # resolved on import to avoid a settings call per row
            )
        )
    return items


async def import_item(client: EsClient, kind: ItemKind, name: str) -> ImportResult:
    """Resolve one item to a mapping plus ILM-derived prefill and suggestions."""
    mappings, ilm_policy = await _resolve(client, kind, name)
    timestamp_field = _detect_timestamp(mappings)
    suggestions = await _ilm_suggestions(client, ilm_policy, timestamp_field)
    return ImportResult(
        index_name=name,
        mapping={"mappings": mappings},
        config_prefill=_prefill(timestamp_field),
        suggestions=tuple(suggestions),
    )


async def _resolve(
    client: EsClient, kind: ItemKind, name: str
) -> tuple[Mapping[str, Any], str | None]:
    if kind == "template":
        return await _resolve_template(client, name)
    if kind == "datastream":
        return await _resolve_data_stream(client, name)
    if kind == "index":
        return await _resolve_index(client, name)
    raise ValueError(f"unknown item kind: {kind}")


async def _resolve_template(client: EsClient, name: str) -> tuple[Mapping[str, Any], str | None]:
    simulated = await client.post_json(f"/_index_template/_simulate/{name}")
    template = simulated.get("template", {})
    return template.get("mappings", {}), _ilm_from_settings(template.get("settings", {}))


async def _resolve_data_stream(client: EsClient, name: str) -> tuple[Mapping[str, Any], str | None]:
    listing = await client.get_json(f"/_data_stream/{name}")
    streams = listing.get("data_streams", [])
    ilm_policy = streams[0].get("ilm_policy") if streams else None
    mapping_response = await client.get_json(f"/{name}/_mapping")
    return _write_index_mappings(mapping_response), ilm_policy


async def _resolve_index(client: EsClient, name: str) -> tuple[Mapping[str, Any], str | None]:
    mapping_response = await client.get_json(f"/{name}/_mapping")
    mappings = mapping_response.get(name, {}).get("mappings", {})
    settings_response = await client.get_json(f"/{name}/_settings")
    settings = settings_response.get(name, {}).get("settings", {})
    return mappings, _ilm_from_settings(settings)


async def _ilm_suggestions(
    client: EsClient, policy_name: str | None, timestamp_field: str | None
) -> list[str]:
    if not policy_name:
        return []
    payload = await client.get_json(f"/_ilm/policy/{policy_name}")
    body = payload.get(policy_name, {}).get("policy", {})
    return translate_ilm(body, timestamp_field)


def _write_index_mappings(mapping_response: Mapping[str, Any]) -> Mapping[str, Any]:
    """A data stream's _mapping is keyed by backing index; the write index sorts last."""
    if not mapping_response:
        return {}
    last_index = sorted(mapping_response)[-1]
    mappings = mapping_response[last_index].get("mappings", {})
    return mappings if isinstance(mappings, Mapping) else {}


def _ilm_from_settings(settings: Mapping[str, Any]) -> str | None:
    index = settings.get("index")
    if isinstance(index, Mapping):
        name = index.get("lifecycle", {}).get("name")
        if isinstance(name, str):
            return name
    flattened = settings.get("index.lifecycle.name")
    return flattened if isinstance(flattened, str) else None


def _detect_timestamp(mappings: Mapping[str, Any]) -> str | None:
    properties = mappings.get("properties", {})
    if "@timestamp" in properties:
        return "@timestamp"
    for field_name, spec in properties.items():
        if isinstance(spec, Mapping) and spec.get("type") in ("date", "date_nanos"):
            return str(field_name)
    return None


def _prefill(timestamp_field: str | None) -> Mapping[str, Any]:
    if not timestamp_field:
        return {}
    return {
        "timestamp_field": timestamp_field,
        "order_by": [timestamp_field],
        "partition_by": f"toYYYYMM(`{timestamp_field}`)",
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
