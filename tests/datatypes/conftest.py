"""Fixtures + wiring for the datatype torture suite.

- registers the ``clickhouse`` marker (Tier-2 live round-trip),
- exposes a session-scoped :class:`ClickHouseClient`, skipping when CH is down,
- writes ``FINDINGS.md`` next to this file at the end of the run.
"""

from __future__ import annotations

import os
import sys

import pytest

# Make sibling helper modules importable as top-level (_typemap, _oracle, ...).
sys.path.insert(0, os.path.dirname(__file__))

from _ch_client import ClickHouseClient
from _findings import render_report

_REPORT_PATH = os.path.join(os.path.dirname(__file__), "FINDINGS.md")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "clickhouse: live round-trip against docker ClickHouse (opt-in)"
    )


@pytest.fixture(scope="session")
def ch() -> ClickHouseClient:
    client = ClickHouseClient.from_env()
    if not client.available():
        pytest.skip(
            "ClickHouse not reachable (set CH_EXEC_CONTAINER for docker-exec, "
            "or expose the HTTP interface on 8123)"
        )
    return client


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    report = render_report()
    with open(_REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(report)
    terminalreporter.write_line(f"datatype findings written to {_REPORT_PATH}")
