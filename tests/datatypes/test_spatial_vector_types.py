"""Tier-1: spatial, vector and ranking types (mostly judgment calls)."""

import pytest
from _findings import check_core_type
from _folds import top_level
from _run import rendered
from _typemap import GROUND_TRUTH

SPATIAL = ["geo_point", "point", "geo_shape", "shape"]
VECTOR_RANK = ["dense_vector", "sparse_vector", "rank_feature", "rank_features"]


def _check(es_type: str) -> None:
    case = top_level(es_type)
    _, type_str = rendered(case)
    check_core_type(GROUND_TRUTH[es_type], case.target, type_str)


@pytest.mark.parametrize("es_type", SPATIAL)
def test_spatial_core_type(es_type: str) -> None:
    _check(es_type)


@pytest.mark.parametrize("es_type", VECTOR_RANK)
def test_vector_rank_core_type(es_type: str) -> None:
    _check(es_type)
