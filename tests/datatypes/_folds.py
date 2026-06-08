"""Cartesian fold builders: wrap one ES type into many contexts and modifiers.

A ``Case`` couples an ES mapping + converter config with the column to inspect
and whether an ``Array(...)`` wrap of the core type is also faithful (true when
the field sits in an array-bearing context). The fold over
{types} x {contexts} and {types} x {modifiers} is what pushes the suite past
~140 parametrized cases.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from _samples import FIELD_MAPPING

_TS = {"@timestamp": {"type": "date"}}
_BASE_CONFIG: dict[str, Any] = {"order_by": ["@timestamp"]}


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    es_type: str
    mapping: dict[str, Any]
    config: dict[str, Any]
    target: str
    array_context: bool = False
    note: str = ""


def _props(**fields: Any) -> dict[str, Any]:
    return {"properties": {**_TS, **fields}}


def _field(es_type: str, **extra: Any) -> dict[str, Any]:
    f = copy.deepcopy(FIELD_MAPPING[es_type])
    f.update(extra)
    return f


# --- contexts ----------------------------------------------------------------
def top_level(es_type: str) -> Case:
    fld = f"{es_type}_f"
    return Case(
        case_id=f"{es_type}@top",
        es_type=es_type,
        mapping=_props(**{fld: _field(es_type)}),
        config=dict(_BASE_CONFIG),
        target=fld,
    )


def in_object(es_type: str) -> Case:
    """Plain object -> flattens to ``obj_leaf`` by default."""
    mapping = _props(obj={"properties": {"leaf": _field(es_type)}})
    return Case(
        case_id=f"{es_type}@object",
        es_type=es_type,
        mapping=mapping,
        config=dict(_BASE_CONFIG),
        target="obj_leaf",
    )


def in_nested(es_type: str) -> Case:
    """Nested forced to flatten -> array column ``n_leaf``."""
    mapping = _props(n={"type": "nested", "properties": {"leaf": _field(es_type)}})
    return Case(
        case_id=f"{es_type}@nested",
        es_type=es_type,
        mapping=mapping,
        config={**_BASE_CONFIG, "flatten_fields": ["n"]},
        target="n_leaf",
        array_context=True,
    )


def multi_field(es_type: str) -> Case:
    """Field carrying a multi-field sub-field; the parent type must survive."""
    fld = f"{es_type}_mf"
    parent = _field(es_type, fields={"kw": {"type": "keyword"}})
    return Case(
        case_id=f"{es_type}@multifield",
        es_type=es_type,
        mapping=_props(**{fld: parent}),
        config=dict(_BASE_CONFIG),
        target=fld,
    )


CONTEXT_TYPES = ("integer", "long", "double", "keyword", "text", "boolean", "ip", "date")


def context_cases() -> list[Case]:
    cases: list[Case] = []
    for t in CONTEXT_TYPES:
        cases.extend((in_object(t), multi_field(t), in_nested(t)))
    return cases


# --- modifiers ---------------------------------------------------------------
_NULL_VALUE = {
    "keyword": "N/A",
    "integer": -1,
    "long": -1,
    "double": -1.0,
    "boolean": False,
    "ip": "0.0.0.0",
    "date": "1970-01-01",
}


def _modified(es_type: str, label: str, **extra: Any) -> Case:
    fld = f"{es_type}_{label}"
    return Case(
        case_id=f"{es_type}@{label}",
        es_type=es_type,
        mapping=_props(**{fld: _field(es_type, **extra)}),
        config=dict(_BASE_CONFIG),
        target=fld,
        note=label,
    )


MODIFIER_TYPES = ("keyword", "integer", "double", "boolean", "ip", "date")


def modifier_cases() -> list[Case]:
    cases: list[Case] = []
    for t in MODIFIER_TYPES:
        cases.append(_modified(t, "index_false", index=False))
        cases.append(_modified(t, "doc_values_false", doc_values=False))
        if t in _NULL_VALUE:
            cases.append(_modified(t, "null_value", null_value=_NULL_VALUE[t]))
    # ignore_above only applies to keyword-family
    cases.append(_modified("keyword", "ignore_above", ignore_above=256))
    return cases


# convenience export for parametrize ids
def case_id(case: Case) -> str:
    return case.case_id
