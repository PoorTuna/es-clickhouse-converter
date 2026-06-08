"""Tier-1: range family + histogram / aggregate_metric_double / percolator.

All are judgment calls -- ES stores a compound shape with no single canonical CH
home -- so the expectation accepts any faithful representation.
"""

import pytest
from _findings import check_core_type
from _folds import top_level
from _run import rendered
from _typemap import GROUND_TRUTH

RANGES = ["integer_range", "long_range", "float_range", "double_range", "date_range", "ip_range"]
COMPOUND = ["histogram", "aggregate_metric_double", "percolator"]


def _check(es_type: str) -> None:
    case = top_level(es_type)
    _, type_str = rendered(case)
    check_core_type(GROUND_TRUTH[es_type], case.target, type_str)


@pytest.mark.parametrize("es_type", RANGES)
def test_range_core_type(es_type: str) -> None:
    _check(es_type)


@pytest.mark.parametrize("es_type", COMPOUND)
def test_compound_core_type(es_type: str) -> None:
    _check(es_type)
