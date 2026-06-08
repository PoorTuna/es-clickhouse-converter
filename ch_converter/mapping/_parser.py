"""Parse a raw Elasticsearch ``_mapping`` JSON into a :class:`MappingModel`.

Accepts either the full ``GET /<index>/_mapping`` response
(``{"idx": {"mappings": {...}}}``) or a bare ``{"properties": {...}}`` block.
No ClickHouse knowledge lives here - this layer only understands ES.
"""

from typing import Any

from ._dynamic import (
    has_dynamic_templates,
    is_alias,
    is_nested,
    normalize_dynamic,
    routes_to_json,
    runtime_field_names,
)
from ._models import EsField, JsonRoot, MappingModel, NestedGroup


def parse_mapping(raw: dict[str, Any]) -> MappingModel:
    mappings = _locate_mappings(raw)

    fields: list[EsField] = []
    json_roots: list[JsonRoot] = []
    nested_groups: list[NestedGroup] = []
    warnings: list[str] = []

    properties = mappings.get("properties", {})
    if not isinstance(properties, dict):
        warnings.append("top-level 'properties' is not an object; no fields parsed")
        properties = {}

    _walk(
        properties,
        prefix="",
        fields=fields,
        json_roots=json_roots,
        nested_groups=nested_groups,
        warnings=warnings,
    )

    return MappingModel(
        fields=tuple(fields),
        json_roots=tuple(json_roots),
        nested_groups=tuple(nested_groups),
        runtime_fields=runtime_field_names(mappings),
        root_dynamic=normalize_dynamic(mappings),
        has_dynamic_templates=has_dynamic_templates(mappings),
        warnings=tuple(warnings),
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
    json_roots: list[JsonRoot],
    nested_groups: list[NestedGroup],
    warnings: list[str],
) -> None:
    for name, node in properties.items():
        path = f"{prefix}{name}"
        if not isinstance(node, dict):
            continue

        if routes_to_json(node):
            json_roots.append(_build_json_root(path, node, warnings))
            continue

        if is_nested(node):
            nested_groups.append(_build_nested_group(path, node, json_roots, warnings))
            continue

        if is_alias(node):
            warnings.append(_alias_skip_warning(path))
            continue

        children = _child_properties(node, path, warnings)
        if children is not None:
            _walk(
                children,
                prefix=f"{path}.",
                fields=fields,
                json_roots=json_roots,
                nested_groups=nested_groups,
                warnings=warnings,
            )
            continue

        fields.append(_build_field(path, node))


def _child_properties(
    node: dict[str, Any], path: str, warnings: list[str]
) -> dict[str, Any] | None:
    """Return a node's ``properties`` only when it is a usable object subtree.

    A non-dict ``properties`` is malformed; warn and treat the node as a leaf
    (return ``None``) rather than crashing on ``.items()``.
    """
    children = node.get("properties")
    if children is None:
        return None
    if not isinstance(children, dict):
        warnings.append(f"{path}: ignored non-object 'properties'")
        return None
    return children


def _build_json_root(path: str, node: dict[str, Any], warnings: list[str]) -> JsonRoot:
    """A JSON column plus the leaves ES still declared under it, used as typed
    path hints. Deeper dynamic/disabled/nested pockets carry no flat scalar
    schema and are skipped - the enclosing JSON column already covers them.
    """
    properties = _child_properties(node, path, warnings) or {}
    leaves = _declared_leaves(properties, prefix=f"{path}.", warnings=warnings)
    return JsonRoot(path=path, fields=tuple(leaves))


def _declared_leaves(
    properties: dict[str, Any], *, prefix: str, warnings: list[str]
) -> list[EsField]:
    leaves: list[EsField] = []
    for name, node in properties.items():
        if not isinstance(node, dict) or routes_to_json(node) or is_nested(node):
            continue
        path = f"{prefix}{name}"
        if is_alias(node):
            warnings.append(_alias_skip_warning(path))
            continue
        children = _child_properties(node, path, warnings)
        if children is not None:
            leaves.extend(_declared_leaves(children, prefix=f"{path}.", warnings=warnings))
            continue
        leaves.append(_build_field(path, node))
    return leaves


def _build_nested_group(
    path: str, node: dict[str, Any], json_roots: list[JsonRoot], warnings: list[str]
) -> NestedGroup:
    """Collect a ``type: nested`` subtree's scalar leaves into one group.

    Inner objects and nested fields flatten into the same group (their leaves
    become parallel-array sub-columns); only ``dynamic``/``enabled: false``
    pockets break out to the index-level JSON roots.
    """
    properties = _child_properties(node, path, warnings) or {}
    leaves: list[EsField] = []
    _collect_leaves(
        properties, prefix=f"{path}.", leaves=leaves, json_roots=json_roots, warnings=warnings
    )
    return NestedGroup(path=path, fields=tuple(leaves))


def _collect_leaves(
    properties: dict[str, Any],
    *,
    prefix: str,
    leaves: list[EsField],
    json_roots: list[JsonRoot],
    warnings: list[str],
) -> None:
    for name, node in properties.items():
        path = f"{prefix}{name}"
        if not isinstance(node, dict):
            continue

        if routes_to_json(node):
            json_roots.append(_build_json_root(path, node, warnings))
            continue

        if is_alias(node):
            warnings.append(_alias_skip_warning(path))
            continue

        children = _child_properties(node, path, warnings)
        if children is not None:
            _collect_leaves(
                children, prefix=f"{path}.", leaves=leaves, json_roots=json_roots, warnings=warnings
            )
            continue

        leaves.append(_build_field(path, node))


def _alias_skip_warning(path: str) -> str:
    return (
        f"{path}: field alias skipped - ES aliases point at another field and "
        f"store no data, so no ClickHouse column is emitted"
    )


def _build_field(path: str, node: dict[str, Any]) -> EsField:
    return EsField(
        path=path,
        es_type=node.get("type", "object"),
        indexed=node.get("index", True) is not False,
        doc_values=node.get("doc_values", True) is not False,
        has_keyword_subfield=_has_keyword_subfield(node),
        date_format=node.get("format"),
        null_value=node.get("null_value"),
        metrics=_metrics(node),
    )


def _metrics(node: dict[str, Any]) -> tuple[str, ...]:
    metrics = node.get("metrics")
    if isinstance(metrics, list):
        return tuple(m for m in metrics if isinstance(m, str))
    return ()


def _has_keyword_subfield(node: dict[str, Any]) -> bool:
    subfields = node.get("fields")
    if not isinstance(subfields, dict):
        return False
    return any(isinstance(sub, dict) and sub.get("type") == "keyword" for sub in subfields.values())
