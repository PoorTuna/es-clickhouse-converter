import ssl

import ch_converter.elasticsearch._client as client_module
from ch_converter.elasticsearch._client import build_verify
from ch_converter.elasticsearch._models import EsConnection


def _connection(**overrides) -> EsConnection:
    base = {
        "base_url": "https://es.example:9200",
        "username": "u",
        "password": "p",
        "tls_enabled": True,
        "ca_cert": None,
    }
    base.update(overrides)
    return EsConnection(**base)


class TestBuildVerify:
    def test_http_ignores_tls_settings(self):
        connection = _connection(base_url="http://es.example:9200", tls_enabled=False)
        assert build_verify(connection) is True

    def test_https_with_verification_disabled_skips_check(self):
        assert build_verify(_connection(tls_enabled=False)) is False

    def test_https_with_system_cas(self):
        assert build_verify(_connection(tls_enabled=True, ca_cert=None)) is True

    def test_https_with_ca_pem_builds_context(self, monkeypatch):
        loaded: dict[str, str] = {}

        class FakeContext:
            def load_verify_locations(self, cadata: str) -> None:
                loaded["cadata"] = cadata

        fake = FakeContext()
        monkeypatch.setattr(client_module.ssl, "create_default_context", lambda: fake)

        result = build_verify(_connection(ca_cert="-----PEM-----"))

        assert result is fake
        assert loaded["cadata"] == "-----PEM-----"

    def test_real_invalid_pem_raises(self):
        # Sanity: a malformed CA is rejected by the stdlib, not silently ignored.
        try:
            build_verify(_connection(ca_cert="not a certificate"))
        except ssl.SSLError:
            return
        raise AssertionError("expected ssl.SSLError for malformed CA PEM")
