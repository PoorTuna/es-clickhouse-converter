"""Predicates for Elasticsearch dynamic-mapping behaviour.

ES keeps adding fields after a mapping is exported (``dynamic: true``,
``dynamic_templates``, ``runtime`` fields). Those open-ended subtrees map to a
ClickHouse ``JSON`` column, which auto-materialises sub-columns on insert - the
direct analogue of ES dynamic mapping. ``dynamic: strict`` stays fully typed.
"""

from typing import Any

_DYNAMIC_JSON_VALUES = frozenset({"true", "runtime"})
_DYNAMIC_TYPED_VALUES = frozenset({"false", "strict"})


def routes_to_json(node: dict[str, Any]) -> bool:
    """True when a subtree's children should collapse into a JSON column."""
    return _is_dynamic_subtree(node) or node.get("enabled") is False


def is_nested(node: dict[str, Any]) -> bool:
    """True for an ES ``type: nested`` array-of-objects with a fixed schema.

    These map to a ClickHouse ``Nested(...)`` column (parallel arrays), the
    analogue that preserves per-element correlation. A nested subtree that is
    also ``dynamic`` routes to JSON instead - checked first by the caller.
    """
    return node.get("type") == "nested"


def _is_dynamic_subtree(node: dict[str, Any]) -> bool:
    dynamic = node.get("dynamic")
    if isinstance(dynamic, bool):
        return dynamic
    if isinstance(dynamic, str):
        return dynamic.lower() in _DYNAMIC_JSON_VALUES
    return False


def normalize_dynamic(node: dict[str, Any]) -> str | None:
    """Return the ``dynamic`` setting as a lowercase string, or ``None``."""
    dynamic = node.get("dynamic")
    if isinstance(dynamic, bool):
        return "true" if dynamic else "false"
    if isinstance(dynamic, str):
        return dynamic.lower()
    return None


def runtime_field_names(mappings: dict[str, Any]) -> tuple[str, ...]:
    runtime = mappings.get("runtime")
    if isinstance(runtime, dict):
        return tuple(runtime.keys())
    return ()


def has_dynamic_templates(mappings: dict[str, Any]) -> bool:
    return bool(mappings.get("dynamic_templates"))
