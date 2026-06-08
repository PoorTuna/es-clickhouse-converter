"""Tier-1: container / relational types.

These do not resolve to a single scalar core type, so each is checked against
its faithful structural outcome rather than the scalar table.
"""

from _extract import column_type, column_types
from _findings import check_absent
from _folds import Case, top_level
from _run import rendered
from _typemap import core_of

from ch_converter.conversion import DdlArtifacts


def _ddl(es_type: str) -> tuple[Case, DdlArtifacts]:
    case = top_level(es_type)
    artifacts, _ = rendered(case)
    return case, artifacts


def test_object_flattens_or_jsons_its_leaf() -> None:
    """A plain object must preserve its leaf: flattened to ``object_f_leaf`` or
    routed to a JSON column on ``object_f``."""
    _, art = _ddl("object")
    cols = column_types(art.ddl)
    flattened = "object_f_leaf" in cols
    jsonified = "object_f" in cols and cols["object_f"].startswith("JSON")
    assert flattened or jsonified, f"object leaf lost; columns={cols}"


def test_nested_is_array_bearing() -> None:
    _, art = _ddl("nested")
    rendered_type = column_type(art.ddl, "nested_f") or ""
    assert rendered_type.startswith("Nested(") or rendered_type.startswith("Array("), rendered_type


def test_flattened_is_map_or_json() -> None:
    """``flattened`` is arbitrary string k/v -> Map(String, String) or JSON."""
    _, art = _ddl("flattened")
    core = core_of(column_type(art.ddl, "flattened_f") or "")
    assert core.startswith("Map(") or core.startswith("JSON"), core


def test_passthrough_preserves_leaf() -> None:
    _, art = _ddl("passthrough")
    cols = column_types(art.ddl)
    assert "passthrough_f_leaf" in cols or "passthrough_f" in cols, cols


def test_join_emits_some_storage() -> None:
    """join is a judgment call; at minimum the relation must land somewhere."""
    _, art = _ddl("join")
    cols = column_types(art.ddl)
    assert any(name.startswith("join_f") for name in cols), cols


def test_alias_emits_no_column() -> None:
    """alias points at another field and stores nothing of its own."""
    case, art = _ddl("alias")
    check_absent("alias", case.target, column_type(art.ddl, case.target))
