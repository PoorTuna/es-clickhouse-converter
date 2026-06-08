"""Resolve each ES object root to exactly one ClickHouse routing strategy.

Detected defaults (``json`` for dynamic subtrees, ``nested`` for ES nested
arrays) and explicit per-root config are collapsed here so no root is ever
emitted as two columns. Object routes are then hoisted to their top-level ES
key: ClickHouse maps a top-level JSON input key to one column, so a route
detected or pinned at a nested path (``product.headers``) must own the whole
``product`` subtree as a single column - otherwise re-ingesting the original
document never populates it. The DDL builder consumes the resulting routes.
"""

from dataclasses import dataclass

from ..mapping import EsField, MappingModel
from ._config import IndexConfig


@dataclass(frozen=True, slots=True)
class ObjectRoute:
    """One object root's resolved routing: exactly one strategy per root.

    ``source`` is ``object`` for a plain/dynamic object or ``array`` for an ES
    ``type: nested`` (array of sub-documents). ``detected`` is the strategy ES
    dictates by default (``json``/``nested``), or ``None`` for a plain object.
    """

    path: str
    strategy: str
    leaves: tuple[EsField, ...]
    source: str
    detected: str | None
    map_value_type: str | None = None


def resolve_object_routes(
    mapping: MappingModel,
    config: IndexConfig,
    warnings: list[str],
    suggestions: list[str],
) -> list[ObjectRoute]:
    """Collapse detected defaults and explicit config into one strategy per
    object root, so no root is ever emitted as two columns."""
    detected = _detected_routes(mapping)
    explicit, map_values = _explicit_strategies(config)

    routes: list[ObjectRoute] = []
    for path in (*detected, *(p for p in explicit if p not in detected)):
        det_strategy, source, det_leaves = detected.get(path, (None, "object", None))
        leaves = det_leaves if det_leaves is not None else _plain_leaves(mapping, path)
        strategy = explicit.get(path, det_strategy or "flatten")
        strategy = _honor_strategy(path, strategy, source, det_strategy, warnings, suggestions)
        routes.append(
            ObjectRoute(
                path=path,
                strategy=strategy,
                leaves=leaves,
                source=source,
                detected=det_strategy,
                map_value_type=map_values.get(path),
            )
        )
    return _hoist_to_top_level(mapping, routes, warnings)


def typed_fields_for_routes(
    mapping: MappingModel, routes: list[ObjectRoute]
) -> tuple[EsField, ...]:
    """Flat scalar columns: ``mapping.fields`` minus any claimed by a
    json/map/nested route, plus the leaves of a detected object flattened by
    override (those never lived in ``mapping.fields``)."""
    claimed = tuple(route.path for route in routes if route.strategy != "flatten")
    base = tuple(field for field in mapping.fields if not under_any(field.path, claimed))
    extra = tuple(
        leaf
        for route in routes
        if route.strategy == "flatten" and route.source == "object" and route.detected
        for leaf in route.leaves
    )
    return base + extra


def under_any(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(f"{root}.") for root in roots)


def _detected_routes(
    mapping: MappingModel,
) -> dict[str, tuple[str, str, tuple[EsField, ...]]]:
    detected: dict[str, tuple[str, str, tuple[EsField, ...]]] = {
        root.path: ("json", "object", root.fields) for root in mapping.json_roots
    }
    for group in mapping.nested_groups:
        detected[group.path] = ("nested", "array", group.fields)
    return detected


def _explicit_strategies(config: IndexConfig) -> tuple[dict[str, str], dict[str, str]]:
    """User-pinned strategy per root, applying ``json > map > nested > flatten``
    precedence when raw config lists a path more than once."""
    explicit: dict[str, str] = {}
    for path in config.json_fields:
        explicit.setdefault(path, "json")
    for path in config.map_fields:
        explicit.setdefault(path, "map")
    for path in config.nested_fields:
        explicit.setdefault(path, "nested")
    for path in config.flatten_fields:
        explicit.setdefault(path, "flatten")
    return explicit, dict(config.map_fields)


def _honor_strategy(
    path: str,
    strategy: str,
    source: str,
    detected: str | None,
    warnings: list[str],
    suggestions: list[str],
) -> str:
    """Resolve unsupported combinations and warn about lossy overrides."""
    if strategy == "map" and source == "array":
        warnings.append(
            f"'{path}' is an ES nested array - Map isn't supported; kept as Nested(...)"
        )
        strategy = "nested"
    if detected == "json" and strategy != "json":
        suggestions.append(
            f"'{path}' was ES-dynamic; routing it to {strategy} drops the open-ended "
            "catch-all - new fields won't be captured (keep it JSON, or add "
            "config.json_fields for a separate catch-all column)"
        )
    return strategy


def _plain_leaves(mapping: MappingModel, root: str) -> tuple[EsField, ...]:
    return tuple(field for field in mapping.fields if field.path.startswith(f"{root}."))


_STRATEGY_PRECEDENCE = {"json": 0, "nested": 1, "map": 2}


def _hoist_to_top_level(
    mapping: MappingModel, routes: list[ObjectRoute], warnings: list[str]
) -> list[ObjectRoute]:
    """Re-root every object route at its top-level ES key, merging routes that
    share one. Flatten routes pass through untouched (they stay scalar columns
    and are out of scope for the top-level-key rule)."""
    passthrough = [route for route in routes if route.strategy == "flatten"]

    groups: dict[str, list[ObjectRoute]] = {}
    for route in routes:
        if route.strategy != "flatten":
            groups.setdefault(_top_level_key(route.path), []).append(route)

    merged = [_merge_group(mapping, top, members, warnings) for top, members in groups.items()]
    return merged + passthrough


def _merge_group(
    mapping: MappingModel, top: str, members: list[ObjectRoute], warnings: list[str]
) -> ObjectRoute:
    winner = min((member.strategy for member in members), key=_STRATEGY_PRECEDENCE.__getitem__)
    _warn_folded(top, winner, members, warnings)
    return ObjectRoute(
        path=top,
        strategy=winner,
        leaves=_all_leaves_under(mapping, top, members),
        # An ES nested array keeps its array-ness so JSON stays bare (scalar path
        # hints would misrepresent its array leaves); plain objects emit hints.
        source="array" if any(member.source == "array" for member in members) else "object",
        detected=_detected_for(top, mapping),
        map_value_type=_map_value_for(winner, members),
    )


def _warn_folded(
    top: str, winner: str, members: list[ObjectRoute], warnings: list[str]
) -> None:
    for member in members:
        if member.strategy != winner and member.path != top:
            warnings.append(
                f"'{member.path}' ({member.strategy}) folded into top-level column "
                f"'{top}' as {winner}; ClickHouse maps the top-level key '{top}' to "
                f"one column"
            )


def _all_leaves_under(
    mapping: MappingModel, top: str, members: list[ObjectRoute]
) -> tuple[EsField, ...]:
    """Every scalar leaf under ``top``, deduped by path, first-seen order. The
    top key itself is never a leaf, so a property-less object stays empty and is
    skipped downstream."""
    prefix = f"{top}."
    leaves: dict[str, EsField] = {}
    sources = [mapping.fields]
    sources += [root.fields for root in mapping.json_roots]
    sources += [group.fields for group in mapping.nested_groups]
    sources += [member.leaves for member in members]
    for fields in sources:
        for field in fields:
            if field.path.startswith(prefix):
                leaves.setdefault(field.path, field)
    return tuple(leaves.values())


def _map_value_for(winner: str, members: list[ObjectRoute]) -> str | None:
    if winner != "map":
        return None
    return next(
        (member.map_value_type for member in members if member.map_value_type is not None), None
    )


def _detected_for(top: str, mapping: MappingModel) -> str | None:
    if any(root.path == top for root in mapping.json_roots):
        return "json"
    if any(group.path == top for group in mapping.nested_groups):
        return "nested"
    return None


def _top_level_key(path: str) -> str:
    return path.split(".", 1)[0]
