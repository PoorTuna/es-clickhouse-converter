"""In-memory, non-persistent store of live cluster sessions.

A session owns one ``EsClient`` (and its open connection pool) and is reaped
either by an explicit disconnect or by idle-TTL expiry. Nothing is written to
disk, so credentials live only in process memory for the session's lifetime.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from ._client import EsClient

DEFAULT_TTL_SECONDS = 1800


class SessionError(LookupError):
    """The referenced session is unknown or has expired."""


@dataclass(slots=True)
class _Session:
    session_id: str
    client: EsClient
    last_used: float = field(default_factory=time.monotonic)


class SessionStore:
    """Maps opaque session ids to live cluster clients."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._sessions: dict[str, _Session] = {}

    def create(self, client: EsClient) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = _Session(session_id=session_id, client=client)
        return session_id

    def get(self, session_id: str) -> EsClient:
        """Return the session's client, refreshing its idle timer.

        Raises ``SessionError`` if the id is unknown or already expired.
        """
        session = self._sessions.get(session_id)
        if session is None or self._is_expired(session):
            raise SessionError("session expired")
        session.last_used = time.monotonic()
        return session.client

    async def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.client.aclose()

    async def sweep(self) -> None:
        expired = [s.session_id for s in self._sessions.values() if self._is_expired(s)]
        for session_id in expired:
            await self.remove(session_id)

    async def close_all(self) -> None:
        for session_id in list(self._sessions):
            await self.remove(session_id)

    def _is_expired(self, session: _Session) -> bool:
        return (time.monotonic() - session.last_used) > self._ttl
