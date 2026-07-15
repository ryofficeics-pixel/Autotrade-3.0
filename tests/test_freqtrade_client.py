import httpx
import pytest

from app.freqtrade_client import FreqtradeClient


def make_client(handler) -> FreqtradeClient:
    client = FreqtradeClient()
    client._client = httpx.AsyncClient(
        base_url="http://testserver", transport=httpx.MockTransport(handler)
    )
    return client


@pytest.mark.asyncio
async def test_login_stores_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/token/login"
        return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1"})

    client = make_client(handler)
    await client.login()
    assert client._access_token == "a1"
    assert client._refresh_token == "r1"


@pytest.mark.asyncio
async def test_get_attaches_bearer_token():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/api/v1/token/login":
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1"})
        assert request.headers["authorization"] == "Bearer a1"
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    result = await client.get("/api/v1/status")
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_expired_token_triggers_refresh_then_retry():
    state = {"access_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/token/login":
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1"})
        if path == "/api/v1/token/refresh":
            return httpx.Response(200, json={"access_token": "a2"})
        if path == "/api/v1/status":
            state["access_calls"] += 1
            if request.headers["authorization"] == "Bearer a1":
                return httpx.Response(401, json={"detail": "expired"})
            assert request.headers["authorization"] == "Bearer a2"
            return httpx.Response(200, json={"ok": True})
        raise AssertionError(f"unexpected path {path}")

    client = make_client(handler)
    result = await client.get("/api/v1/status")
    assert result == {"ok": True}
    assert client._access_token == "a2"
    assert state["access_calls"] == 2


@pytest.mark.asyncio
async def test_ping_does_not_require_auth():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"status": "pong"})

    client = make_client(handler)
    result = await client.ping()
    assert result == {"status": "pong"}
