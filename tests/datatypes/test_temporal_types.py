"""Tier-1: date / date_nanos -> DateTime64 (precision is converter policy)."""

import pytest
from _findings import check_core_type
from _folds import top_level
from _run import rendered
from _typemap import GROUND_TRUTH


@pytest.mark.parametrize("es_type", ["date", "date_nanos"])
def test_temporal_core_type(es_type: str) -> None:
    case = top_level(es_type)
    _, type_str = rendered(case)
    check_core_type(GROUND_TRUTH[es_type], case.target, type_str)
