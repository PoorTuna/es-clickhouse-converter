"""Tier-1 cartesian fold: type x {index:false, doc_values:false, null_value,
ignore_above}.

A mapping attribute that does not change the logical type must not change the CH
core type either.
"""

import pytest
from _findings import check_core_type
from _folds import Case, case_id, modifier_cases
from _run import rendered
from _typemap import GROUND_TRUTH

_CASES = modifier_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case_id(c) for c in _CASES])
def test_modifier_keeps_core_type(case: Case) -> None:
    _, type_str = rendered(case)
    check_core_type(GROUND_TRUTH[case.es_type], case.target, type_str)
