"""Minimal live-ClickHouse client for the Tier-2 round-trip check.

ClickHouse itself is the judge: if it accepts the generated DDL and returns the
value we ingested, the type is faithful regardless of what the converter or our
table guessed.

Two transports, no third-party dependency:

* ``HttpTransport`` - the HTTP interface (8123). Works when the ``default`` user
  is reachable from the host.
* ``ExecTransport`` - shells out to ``docker exec <container> clickhouse-client``.
  The stock image restricts ``default`` to localhost, so host HTTP is refused;
  the in-container client connects over the local socket and works. Select it by
  exporting ``CH_EXEC_CONTAINER=<name>``.

The conftest ``ch`` fixture picks a transport from the environment and skips the
Tier-2 suite when neither is reachable.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol


class ClickHouseError(RuntimeError):
    """A ClickHouse statement failed; carries the server's error text."""


class Transport(Protocol):
    def run(self, sql: str, stdin: str | None = None) -> str: ...


class HttpTransport:
    def __init__(self, host: str, port: int, user: str, password: str, timeout: float) -> None:
        # best_effort lets CH parse ISO-8601 dates as ES emits them ('T'/'Z'),
        # mirroring how a real ES->CH ingestion pipeline is configured.
        self._url = f"http://{host}:{port}/?date_time_input_format=best_effort"
        self._headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}
        self._timeout = timeout

    def run(self, sql: str, stdin: str | None = None) -> str:
        body = sql if stdin is None else f"{sql}\n{stdin}"
        request = urllib.request.Request(
            self._url, data=body.encode("utf-8"), method="POST", headers=self._headers
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                text: str = resp.read().decode("utf-8")
                return text
        except urllib.error.HTTPError as exc:
            raise ClickHouseError(exc.read().decode("utf-8", "replace").strip()) from exc


class ExecTransport:
    def __init__(self, container: str, timeout: float) -> None:
        self._container = container
        self._timeout = timeout

    def run(self, sql: str, stdin: str | None = None) -> str:
        cmd = [
            "docker",
            "exec",
            "-i",
            self._container,
            "clickhouse-client",
            "--date_time_input_format=best_effort",
            "--query",
            sql,
        ]
        proc = subprocess.run(
            cmd,
            input=(stdin or "").encode("utf-8"),
            capture_output=True,
            timeout=self._timeout,
        )
        if proc.returncode != 0:
            raise ClickHouseError(proc.stderr.decode("utf-8", "replace").strip())
        return proc.stdout.decode("utf-8")


class ClickHouseClient:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    @classmethod
    def from_env(cls, timeout: float = 15.0) -> ClickHouseClient:
        container = os.environ.get("CH_EXEC_CONTAINER")
        if container:
            return cls(ExecTransport(container, timeout))
        return cls(
            HttpTransport(
                host=os.environ.get("CH_HOST", "localhost"),
                port=int(os.environ.get("CH_PORT", "8123")),
                user=os.environ.get("CH_USER", "default"),
                password=os.environ.get("CH_PASSWORD", ""),
                timeout=timeout,
            )
        )

    def available(self) -> bool:
        try:
            return self._t.run("SELECT 1").strip() == "1"
        except (OSError, ClickHouseError, subprocess.SubprocessError):
            return False

    def execute(self, sql: str) -> str:
        return self._t.run(sql)

    def insert_json(self, table: str, doc: Mapping[str, Any]) -> None:
        self._t.run(f"INSERT INTO `{table}` FORMAT JSONEachRow", stdin=json.dumps(doc))

    def select_rows(self, sql: str) -> list[dict[str, Any]]:
        text = self._t.run(f"{sql} FORMAT JSONEachRow")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def drop(self, table: str) -> None:
        self.execute(f"DROP TABLE IF EXISTS `{table}`")
