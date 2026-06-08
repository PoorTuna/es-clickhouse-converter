"""HTTP endpoints for connecting to and browsing a live Elasticsearch cluster."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Response

from . import _discovery as discovery
from ._client import EsClient, EsError
from ._discovery import ItemKind
from ._models import EsConnection
from ._schemas import (
    ConnectRequest,
    ConnectResponse,
    DataStreamItem,
    DisconnectRequest,
    ImportResponse,
    IndexItem,
    TemplateItem,
)
from ._session import SessionError, SessionStore

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def register_es_routes(app: FastAPI, store: SessionStore) -> None:
    def client_for(session_id: str) -> EsClient:
        try:
            return store.get(session_id)
        except SessionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.post("/es/connect", response_model=ConnectResponse)
    async def connect(request: ConnectRequest) -> ConnectResponse:
        connection = EsConnection(
            base_url=request.url,
            username=request.username,
            password=request.password,
            tls_enabled=request.tls_enabled,
            ca_cert=request.ca_cert,
        )
        client = EsClient.create(connection)
        try:
            info = await client.info()
        except EsError as exc:
            await client.aclose()
            logger.warning("ES connect failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        session_id = store.create(client)
        return ConnectResponse(
            session_id=session_id, cluster_name=info.cluster_name, version=info.version
        )

    @app.get("/es/templates", response_model=list[TemplateItem])
    async def templates(session_id: str) -> list[TemplateItem]:
        infos = await _guard(discovery.list_templates(client_for(session_id)))
        return [TemplateItem.from_info(info) for info in infos]

    @app.get("/es/datastreams", response_model=list[DataStreamItem])
    async def datastreams(session_id: str) -> list[DataStreamItem]:
        infos = await _guard(discovery.list_data_streams(client_for(session_id)))
        return [DataStreamItem.from_info(info) for info in infos]

    @app.get("/es/indices", response_model=list[IndexItem])
    async def indices(session_id: str, include_system: bool = False) -> list[IndexItem]:
        infos = await _guard(discovery.list_indices(client_for(session_id), include_system))
        return [IndexItem.from_info(info) for info in infos]

    @app.get("/es/import", response_model=ImportResponse)
    async def import_item(session_id: str, kind: ItemKind, name: str) -> ImportResponse:
        result = await _guard(discovery.import_item(client_for(session_id), kind, name))
        return ImportResponse.from_result(result)

    @app.post("/es/disconnect", status_code=204)
    async def disconnect(request: DisconnectRequest) -> Response:
        await store.remove(request.session_id)
        return Response(status_code=204)


async def _guard(awaitable: Awaitable[_T]) -> _T:
    """Surface upstream Elasticsearch failures as 502s."""
    try:
        return await awaitable
    except EsError as exc:
        logger.warning("ES request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
