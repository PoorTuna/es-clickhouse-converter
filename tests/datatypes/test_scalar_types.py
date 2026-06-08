"""Tier-1: top-level scalar ES types must land on a faithful CH core type."""

import pytest
from _findings import check_core_type
from _folds import top_level
from _run import rendered
from _typemap import GROUND_TRUTH

NUMERIC = [
    "byte",
    "short",
    "integer",
    "long",
    "unsigned_long",
    "float",
    "half_float",
    "double",
    "scaled_float",
]
KEYWORD_FAMILY = ["keyword", "constant_keyword", "wildcard"]
TEXT_FAMILY = [
    "text",
    "match_only_text",
    "search_as_you_type",
    "annotated_text",
    "completion",
    "semantic_text",
    "token_count",
]
OTHER_SCALAR = ["boolean", "binary", "ip", "version", "murmur3"]


def _check(es_type: str) -> None:
    case = top_level(es_type)
    _, type_str = rendered(case)
    check_core_type(GROUND_TRUTH[es_type], case.target, type_str)


@pytest.mark.parametrize("es_type", NUMERIC)
def test_numeric_core_type(es_type: str) -> None:
    _check(es_type)


@pytest.mark.parametrize("es_type", KEYWORD_FAMILY)
def test_keyword_family_core_type(es_type: str) -> None:
    _check(es_type)


@pytest.mark.parametrize("es_type", TEXT_FAMILY)
def test_text_family_core_type(es_type: str) -> None:
    _check(es_type)


@pytest.mark.parametrize("es_type", OTHER_SCALAR)
def test_other_scalar_core_type(es_type: str) -> None:
    _check(es_type)
