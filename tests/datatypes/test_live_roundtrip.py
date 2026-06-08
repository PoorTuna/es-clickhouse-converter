"""Tier-2 (opt-in, marker ``clickhouse``): execute the generated DDL against a
live ClickHouse 26.3.7 and round-trip a representative document.

This is the strongest, most converter-agnostic oracle: if ClickHouse accepts the
DDL, ingests the ES document value, and returns a row, the type is faithful --
no opinion of ours required. A rejected CREATE TABLE or a refused INSERT is a
real faithfulness finding.

Run with::

    docker compose -f ch_converter/docker-compose.yml up -d clickhouse
    pytest tests/datatypes -m clickhouse
"""

import pytest
from _ch_client import ClickHouseClient, ClickHouseError
from _findings import FINDINGS, Finding
from _samples import FIELD_MAPPING, SAMPLE_VALUE
from _typemap import GROUND_TRUTH, scalar_expectations

from ch_converter.conversion import convert_index

pytestmark = pytest.mark.clickhouse

# Single-column types: a document value maps onto exactly one column, so a value
# round-trip is well defined. Containers/alias are covered structurally elsewhere.
ROUNDTRIP_TYPES = sorted(scalar_expectations())

# A ClickHouse-friendly sort-key value (ISO 'T'/'Z' is not always parsed).
_TS_VALUE = "2026-06-08 12:00:00.000"


def _record(es_type: str, target: str, detail: str) -> None:
    verdict = "design-choice (review)" if GROUND_TRUTH[es_type].judgment else "likely converter bug"
    FINDINGS.append(
        Finding(
            es_type=es_type,
            target=target,
            expected="executes + round-trips on CH 26.3.7",
            got=detail,
            verdict=verdict,
        )
    )


@pytest.mark.parametrize("es_type", ROUNDTRIP_TYPES)
def test_roundtrip(ch: ClickHouseClient, es_type: str) -> None:
    target = f"{es_type}_f"
    table = f"rt_{es_type}"
    mapping = {"properties": {"@timestamp": {"type": "date"}, target: FIELD_MAPPING[es_type]}}
    ddl = convert_index(table, mapping, {"order_by": ["@timestamp"]}).ddl

    ch.drop(table)
    try:
        ch.execute(ddl)
    except ClickHouseError as exc:
        _record(es_type, target, f"CREATE failed: {exc}")
        pytest.fail(f"{es_type}: CREATE TABLE rejected by ClickHouse: {exc}")

    doc = {"@timestamp": _TS_VALUE, target: SAMPLE_VALUE[es_type]}
    try:
        ch.insert_json(table, doc)
        rows = ch.select_rows(f"SELECT * FROM `{table}`")
    except ClickHouseError as exc:
        _record(es_type, target, f"INSERT/SELECT failed: {exc}")
        pytest.fail(f"{es_type}: ClickHouse refused the document value: {exc}")
    finally:
        ch.drop(table)

    assert len(rows) == 1, f"{es_type}: expected 1 row, got {len(rows)}"
    assert target in rows[0], f"{es_type}: column {target} missing from read-back"
