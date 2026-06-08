"""Tier-1 extremes: collisions, reserved words, unicode, depth, width, dynamic.

These stress the renderer's structural correctness rather than per-type mapping.
"""

import pytest
from _extract import column_types

from ch_converter.conversion import DdlArtifacts, convert_index

_TS = {"@timestamp": {"type": "date"}}
_CFG = {"order_by": ["@timestamp"]}


def _convert(props: dict, cfg: dict | None = None) -> DdlArtifacts:
    return convert_index("edge", {"properties": {**_TS, **props}}, {**_CFG, **(cfg or {})})


def test_dotted_path_and_underscore_collide_safely() -> None:
    """``a.b`` (object) and a literal ``a_b`` both want column ``a_b``; one must
    not silently clobber the other."""
    art = _convert(
        {
            "a": {"properties": {"b": {"type": "keyword"}}},
            "a_b": {"type": "keyword"},
        }
    )
    cols = column_types(art.ddl)
    distinct = len({n for n in cols if n in ("a_b", "a_b_1", "a.b")}) >= 2
    warned = any("collid" in w.lower() or "collision" in w.lower() for w in art.warnings)
    assert distinct or warned, f"collision unhandled: cols={cols} warns={art.warnings}"


@pytest.mark.parametrize("name", ["index", "table", "array", "tuple", "select", "from"])
def test_reserved_clickhouse_keyword_as_field_name(name: str) -> None:
    art = _convert({name: {"type": "keyword"}})
    cols = column_types(art.ddl)
    assert name in cols, cols
    # must be backtick-quoted in the DDL to be valid against a reserved word
    assert f"`{name}`" in art.ddl


def test_unicode_and_emoji_field_name() -> None:
    art = _convert({"naïve_café_🚀": {"type": "keyword"}})
    assert "naïve_café_🚀" in column_types(art.ddl)


def test_deeply_nested_object_flattens() -> None:
    """6 levels of plain objects -> one dotted/underscored leaf column."""
    node: dict = {"type": "keyword"}
    for level in ("l4", "l3", "l2", "l1"):
        node = {"properties": {level: node}}
    art = _convert({"root": node})
    cols = column_types(art.ddl)
    assert "root_l1_l2_l3_l4" in cols, cols


def test_wide_table_500_columns() -> None:
    props = {f"c{i}": {"type": "keyword"} for i in range(500)}
    art = _convert(props)
    cols = column_types(art.ddl)
    assert sum(1 for n in cols if n.startswith("c")) == 500


def test_empty_object_does_not_crash() -> None:
    art = _convert({"blob": {"type": "object"}})
    assert "CREATE TABLE" in art.ddl  # no exception, valid statement emitted


@pytest.mark.parametrize("dynamic", ["true", "false", "strict", "runtime"])
def test_dynamic_modes_emit_valid_ddl(dynamic: str) -> None:
    obj = {"type": "object", "dynamic": dynamic, "properties": {"k": {"type": "keyword"}}}
    art = _convert({"obj": obj})
    assert "CREATE TABLE" in art.ddl


def test_runtime_fields_emit_no_storage_column() -> None:
    """Runtime fields are script-computed at query time and store nothing."""
    mapping = {
        "properties": {**_TS, "real": {"type": "keyword"}},
        "runtime": {"computed": {"type": "keyword", "script": {"source": "emit('x')"}}},
    }
    art = convert_index("edge", mapping, _CFG)
    assert "computed" not in column_types(art.ddl)
