"""Tier-1 cartesian fold: type x {object, multi-field, nested}.

The same scalar type is dropped into each structural context; its core CH type
must survive (an ``Array(...)`` wrap is also faithful in the nested context,
where ES values are arrays of objects).
"""

import pytest
from _findings import check_core_type
from _folds import Case, case_id, context_cases
from _run import rendered
from _typemap import GROUND_TRUTH

_CASES = context_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case_id(c) for c in _CASES])
def test_type_survives_context(case: Case) -> None:
    _, type_str = rendered(case)
    check_core_type(
        GROUND_TRUTH[case.es_type],
        case.target,
        type_str,
        array_context=case.array_context,
    )
