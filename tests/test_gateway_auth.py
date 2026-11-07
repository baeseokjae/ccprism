"""Regression tests for the real HTTP authentication boundary (no upstream calls)."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from authlib.jose import jwt
from fastapi.testclient import TestClient

from src.auth import gateway_auth
from src.config import AuthSettings, GatewaySettings, ServerSettings
from src.main import create_app

MASTER_KEY = "test-master-key-" + "m" * 32
JWT_SECRET = "test-signing-key-" + "s" * 32
PROTECTED_ENDPOINTS = [
    ("POST", "/v1/messages"),
    ("GET", "/admin/rules"),
    ("GET", "/admin/rules/default"),
    ("POST", "/admin/rules/reload"),
    ("GET", "/admin/stats"),
    ("GET", "/admin/costs/daily"),
    ("GET", "/admin/costs/by-provider"),
    ("GET", "/admin/costs/by-rule"),
    ("GET", "/admin/costs/summary"),
    ("GET", "/admin/providers"),
    ("GET", "/auth/status"),
    ("GET", "/oauth/authorize"),
    ("POST", "/oauth/device"),
    ("POST", "/oauth/device/authorize"),
    ("POST", "/oauth/token"),
]


def make_token(**overrides):
    payload = {"sub": "test-user", "role": "user", "exp": int(time.time()) + 60}
    payload.update(overrides)
    return jwt.encode({"alg": "HS256"}, payload, JWT_SECRET).decode()


@pytest.fixture
def settings(monkeypatch):
    settings = GatewaySettings(
        auth=AuthSettings(gateway_master_key=MASTER_KEY, jwt_secret_key=JWT_SECRET)
    )
    monkeypatch.setattr(gateway_auth, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def client(settings):
    app = create_app()
    app.state.litellm_router = MagicMock()
    app.state.litellm_router.acompletion = AsyncMock(return_value=MagicMock(choices=[]))
    # An empty model makes the fake response JSON-serializable.
    app.state.litellm_router.acompletion.return_value = type(
        "Response", (), {"id": "test", "model": "test", "choices": []}
    )()
    return TestClient(app)


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
@pytest.mark.parametrize("headers", [{}, {"x-api-key": "invalid"}])
def test_all_sensitive_endpoints_reject_unauthenticated_requests(client, method, path, headers):
    response = client.request(method, path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    client.app.state.litellm_router.acompletion.assert_not_called()


@pytest.mark.parametrize("header", ["x-api-key", "authorization"])
def test_master_key_can_use_admin_and_proxy(client, header):
    value = MASTER_KEY if header == "x-api-key" else f"Bearer {MASTER_KEY}"
    assert client.get("/admin/stats", headers={header: value}).status_code == 200
    assert client.post("/v1/messages", headers={header: value}, json={}).status_code == 200
    client.app.state.litellm_router.acompletion.assert_awaited_once()


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS[1:])
def test_user_jwt_cannot_access_management(client, method, path):
    response = client.request(method, path, headers={"authorization": f"Bearer {make_token()}"})
    assert response.status_code == 403


def test_user_jwt_can_proxy_and_admin_jwt_can_manage(client):
    assert (
        client.post(
            "/v1/messages", headers={"authorization": f"Bearer {make_token()}"}, json={}
        ).status_code
        == 200
    )
    assert (
        client.get("/admin/stats", headers={"x-api-key": make_token(role="admin")}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": 1},
        {"exp": None},
        {"sub": ""},
        {"sub": None},
        {"role": "owner"},
        {"nbf": int(time.time()) + 3600},
    ],
)
def test_invalid_jwt_claims_rejected(client, overrides):
    assert (
        client.get("/admin/stats", headers={"x-api-key": make_token(**overrides)}).status_code
        == 401
    )


@pytest.mark.parametrize("missing", ["exp", "sub"])
def test_required_jwt_claims(client, missing):
    payload = {"sub": "test-user", "exp": int(time.time()) + 60, "role": "admin"}
    del payload[missing]
    token = jwt.encode({"alg": "HS256"}, payload, JWT_SECRET).decode()
    assert client.get("/admin/stats", headers={"x-api-key": token}).status_code == 401


def test_unexpected_jwt_algorithm_rejected(client):
    token = jwt.encode({"alg": "HS384"}, {"sub": "a", "exp": int(time.time()) + 60}, JWT_SECRET)
    assert client.get("/admin/stats", headers={"x-api-key": token.decode()}).status_code == 401


def test_wrong_jwt_signature_rejected(client):
    token = jwt.encode(
        {"alg": "HS256"}, {"sub": "a", "exp": int(time.time()) + 60}, "wrong-secret" * 4
    )
    assert client.get("/admin/stats", headers={"x-api-key": token.decode()}).status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {"authorization": "Basic abc"},
        {"authorization": "Bearer "},
        {"authorization": f"Bearer  {MASTER_KEY}"},
        {"x-api-key": MASTER_KEY, "authorization": "Bearer invalid"},
        [("x-api-key", MASTER_KEY), ("x-api-key", "invalid")],
        [("authorization", f"Bearer {MASTER_KEY}"), ("authorization", "Bearer invalid")],
    ],
)
def test_ambiguous_or_malformed_headers_rejected(client, headers):
    assert client.get("/admin/stats", headers=headers).status_code == 401


def test_same_token_in_both_headers_is_accepted(client):
    assert (
        client.get(
            "/admin/stats",
            headers={"x-api-key": MASTER_KEY, "authorization": f"Bearer {MASTER_KEY}"},
        ).status_code
        == 200
    )


def test_missing_auth_configuration_fails_closed(client, settings):
    settings.auth.gateway_master_key = ""
    settings.auth.jwt_secret_key = ""
    assert client.get("/admin/stats", headers={"x-api-key": MASTER_KEY}).status_code == 503


def test_auth_enabled_never_bypassed_by_local_mode(client, settings):
    settings.auth.local_mode = True
    assert client.get("/admin/stats").status_code == 503


def test_only_minimal_health_is_public(client):
    assert client.get("/health").json() == {"status": "healthy"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "peer,host,headers,expected",
    [
        ("127.0.0.1", "127.0.0.1", {}, 200),
        ("::1", "localhost", {}, 200),
        ("203.0.113.10", "127.0.0.1", {}, 403),
        ("127.0.0.1", "attacker.example", {}, 403),
        ("127.0.0.1", "localhost", {"sec-fetch-site": "cross-site"}, 403),
        ("127.0.0.1", "127.0.0.1", {"origin": "https://attacker.example"}, 403),
        ("203.0.113.10", "localhost", {"x-forwarded-for": "127.0.0.1"}, 403),
    ],
)
def test_local_opt_out_requires_loopback_peer_and_host(settings, peer, host, headers, expected):
    settings.auth.enabled = False
    settings.auth.local_mode = True
    client = TestClient(create_app(), base_url=f"http://{host}", client=(peer, 12345))
    assert client.get("/admin/stats", headers=headers).status_code == expected


@pytest.mark.parametrize(
    "auth,host",
    [
        (AuthSettings(), "127.0.0.1"),
        (AuthSettings(gateway_master_key="short"), "127.0.0.1"),
        (AuthSettings(jwt_secret_key="short"), "127.0.0.1"),
        (AuthSettings(gateway_master_key=" " * 32), "127.0.0.1"),
        (AuthSettings(enabled=False, local_mode=False), "127.0.0.1"),
        (AuthSettings(enabled=False, local_mode=True), "0.0.0.0"),
        (AuthSettings(enabled=False, local_mode=True), ""),
        (AuthSettings(enabled=False, local_mode=True), "::"),
        (AuthSettings(enabled=False, local_mode=True), "example.com"),
    ],
)
def test_unsafe_startup_settings_rejected(auth, host):
    with pytest.raises(ValueError):
        gateway_auth.validate_auth_settings(
            GatewaySettings(auth=auth, server=ServerSettings(host=host))
        )


def test_real_lifespan_checks_auth_before_loading_credentials(monkeypatch):
    from src import main

    monkeypatch.setattr(main, "get_settings", lambda: GatewaySettings())
    with pytest.raises(ValueError, match="Configure auth"), TestClient(create_app()):
        pass


async def test_legacy_token_verifier_does_not_accept_any_token_in_local_mode(settings):
    settings.auth.local_mode = True
    assert await gateway_auth.verify_gateway_token("not-a-real-key") is None


@pytest.mark.parametrize("claim", ["exp", "nbf", "iat"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True])
def test_invalid_numeric_dates_rejected(client, claim, value):
    token = make_token(**{claim: value})
    assert client.get("/admin/stats", headers={"x-api-key": token}).status_code == 401


def test_oauth_fails_clearly_without_signing_key(client, monkeypatch, settings):
    from src.api import auth_routes

    settings.auth.jwt_secret_key = ""
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    response = client.post(
        "/oauth/device", headers={"x-api-key": MASTER_KEY}, json={"client_id": "development"}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "OAuth requires a configured auth.jwt_secret_key"


def test_oauth_factory_does_not_generate_an_unverifiable_key(monkeypatch):
    from src import config
    from src.auth.oauth_server import create_oauth_server

    monkeypatch.setattr(config, "get_settings", lambda: GatewaySettings())
    with pytest.raises(ValueError, match="configured JWT signing key"):
        create_oauth_server()


@pytest.mark.parametrize("stream", [False, True])
def test_provider_errors_do_not_echo_credentials(client, stream, caplog):
    secret = "sensitive-provider-credential"
    client.app.state.litellm_router.acompletion.side_effect = RuntimeError(secret)
    response = client.post(
        "/v1/messages", headers={"x-api-key": MASTER_KEY}, json={"stream": stream}
    )
    assert response.status_code == (200 if stream else 502)
    assert secret not in response.text
    assert secret not in caplog.text
