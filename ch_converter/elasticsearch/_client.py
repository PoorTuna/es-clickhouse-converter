"""Async HTTP access to a live Elasticsearch cluster.

This is the only module in the project that makes outbound network calls. The
target URL and credentials are user-supplied (the user's own cluster), so this
is an intentional SSRF/credential surface; we deliberately do not allowlist hosts.
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx

from ._models import ClusterInfo, EsConnection

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_LIMITS = httpx.Limits(max_connections=8, max_keepalive_connections=4)


class EsError(RuntimeError):
    """An Elasticsearch request failed (unreachable, auth, or non-2xx status)."""


def build_verify(connection: EsConnection) -> bool | ssl.SSLContext:
    """Resolve httpx's ``verify`` from the connection's TLS settings.

    Plain http ignores the result. For https, ``tls_enabled`` is a verification
    toggle: off skips verification (self-signed clusters), on verifies against
    the supplied CA PEM when given, otherwise the system trust store.
    """
    if not connection.base_url.lower().startswith("https"):
        return True
    if not connection.tls_enabled:
        return False
    if connection.ca_cert:
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=connection.ca_cert)
        return context
    return True


class EsClient:
    """Thin async wrapper over one cluster connection."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @classmethod
    def create(cls, connection: EsConnection) -> EsClient:
        http = httpx.AsyncClient(
            base_url=connection.base_url.rstrip("/"),
            auth=(connection.username, connection.password),
            verify=build_verify(connection),
            timeout=_TIMEOUT,
            limits=_LIMITS,
        )
        return cls(http)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post_json(self, path: str, body: Any | None = None) -> Any:
        return await self._request("POST", path, json=body)

    async def info(self) -> ClusterInfo:
        """Validate reachability and identify the cluster."""
        payload = await self.get_json("/")
        version = payload.get("version", {}).get("number", "unknown")
        return ClusterInfo(cluster_name=payload.get("cluster_name", "unknown"), version=version)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EsError(f"{exc.response.status_code} from {path}: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise EsError(f"cannot reach Elasticsearch ({path}): {exc}") from exc
        return response.json()
