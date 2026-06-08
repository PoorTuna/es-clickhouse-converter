import asyncio

import pytest

from ch_converter.elasticsearch._session import SessionError, SessionStore


class FakeClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class TestSessionStore:
    def test_create_then_get_returns_same_client(self):
        store = SessionStore()
        client = FakeClient()
        session_id = store.create(client)
        assert store.get(session_id) is client

    def test_get_unknown_id_raises(self):
        with pytest.raises(SessionError):
            SessionStore().get("nope")

    def test_expired_session_raises(self):
        store = SessionStore(ttl_seconds=-1)
        session_id = store.create(FakeClient())
        with pytest.raises(SessionError):
            store.get(session_id)

    def test_remove_closes_client_and_forgets_it(self):
        store = SessionStore()
        client = FakeClient()
        session_id = store.create(client)
        asyncio.run(store.remove(session_id))
        assert client.closed is True
        with pytest.raises(SessionError):
            store.get(session_id)

    def test_sweep_reaps_only_expired_sessions(self):
        store = SessionStore(ttl_seconds=-1)
        client = FakeClient()
        store.create(client)
        asyncio.run(store.sweep())
        assert client.closed is True

    def test_close_all_closes_every_client(self):
        store = SessionStore()
        clients = [FakeClient() for _ in range(3)]
        for client in clients:
            store.create(client)
        asyncio.run(store.close_all())
        assert all(client.closed for client in clients)
