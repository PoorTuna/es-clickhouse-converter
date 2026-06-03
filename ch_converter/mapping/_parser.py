"""Parse a raw Elasticsearch ``_mapping`` JSON into a :class:`MappingModel`.

Accepts either the full ``GET /<index>/_mapping`` response
(``{"idx": {"mappings": {...}}}``) or a bare ``{"properties": {...}}`` block.
No ClickHouse knowledge lives here - this layer only understands ES.
"""

from typing import Any

from ._dynamic import (
    has_dynamic_templates,
    is_nested,
    normalize_dynamic,
    routes_to_json,
    runtime_field_names,
)
from ._models import EsField, MappingModel, NestedGroup


def parse_mapping(raw: dict[str, Any]) -> MappingModel:
    mappings = _locate_mappings(raw)
    properties = mappings.get("properties", {})

    fields: list[EsField] = []
    json_roots: list[str] = []
    nested_groups: list[NestedGroup] = []
    _walk(
        properties,
        prefix="",
        fields=fields,
        json_roots=json_roots,
        nested_groups=nested_groups,
    )

    return MappingModel(
        fields=tuple(fields),
        json_roots=tuple(json_roots),
        nested_groups=tuple(nested_groups),
        runtime_fields=runtime_field_names(mappings),
        root_dynamic=normalize_dynamic(mappings),
        has_dynamic_templates=has_dynamic_templates(mappings),
    )


def _locate_mappings(raw: dict[str, Any]) -> dict[str, Any]:
    if "mappings" in raw:
        return dict(raw["mappings"])
    if "properties" in raw or "dynamic" in raw or "runtime" in raw:
        return raw
    # Full response keyed by index name: {"my-index": {"mappings": {...}}}.
    for value in raw.values():
        if isinstance(value, dict) and "mappings" in value:
            return dict(value["mappings"])
    return raw


def _walk(
    properties: dict[str, Any],
    *,
    prefix: str,
    fields: list[EsField],
    json_roots: list[str],
    nested_groups: list[NestedGroup],
) -> None:
    for name, node in properties.items():
        path = f"{prefix}{name}"
        if not isinstance(node, dict):
            continue

        if routes_to_json(node):
            json_roots.append(path)
            continue

        if is_nested(node):
            nested_groups.append(_build_nested_group(path, node, json_roots))
            continue

        children = node.get("properties")
        if children is not None:
            _walk(
                children,
                prefix=f"{path}.",
                fields=fields,
                json_roots=json_roots,
                nested_groups=nested_groups,
            )
            continue

        fields.append(_build_field(path, node))


def _build_nested_group(
    path: str, node: dict[str, Any], json_roots: list[str]
) -> NestedGroup:
    """Collect a ``type: nested`` subtree's scalar leaves into one group.

    Inner objects and nested fields flatten into the same group (their leaves
    become parallel-array sub-columns); only ``dynamic``/``enabled: false``
    pockets break out to the index-level JSON roots.
    """
    leaves: list[EsField] = []
    _collect_leaves(
        node.get("properties", {}), prefix=f"{path}.", leaves=leaves, json_roots=json_roots
    )
    return NestedGroup(path=path, fields=tuple(leaves))


def _collect_leaves(
    properties: dict[str, Any],
    *,
    prefix: str,
    leaves: list[EsField],
    json_roots: list[str],
) -> None:
    for name, node in properties.items():
        path = f"{prefix}{name}"
        if not isinstance(node, dict):
            continue

        if routes_to_json(node):
            json_roots.append(path)
            continue

        children = node.get("properties")
        if children is not None:
            _collect_leaves(children, prefix=f"{path}.", leaves=leaves, json_roots=json_roots)
            continue

        leaves.append(_build_field(path, node))


def _build_field(path: str, node: dict[str, Any]) -> EsField:
    return EsField(
        path=path,
        es_type=node.get("type", "object"),
        indexed=node.get("index", True) is not False,
        doc_values=node.get("doc_values", True) is not False,
        has_keyword_subfield=_has_keyword_subfield(node),
        date_format=node.get("format"),
        null_value=node.get("null_value"),
    )


def _has_keyword_subfield(node: dict[str, Any]) -> bool:
    subfields = node.get("fields")
    if not isinstance(subfields, dict):
        return False
    return any(isinstance(sub, dict) and sub.get("type") == "keyword" for sub in subfields.values())
