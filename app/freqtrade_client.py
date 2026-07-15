"""
Authenticated client for Freqtrade's own REST API (freqtrade.rpc.api_server).

This file contains no trading logic whatsoever - it only knows how to log in and forward
requests to endpoints Freqtrade itself already exposes:

    POST /api/v1/token/login    - JWT login (HTTP Basic auth)
    POST /api/v1/token/refresh  - refresh an expired access token
    GET  /api/v1/ping           - liveness, no auth required
    GET  /api/v1/status         - open trades
    GET  /api/v1/trades         - closed + open trade history
    GET  /api/v1/balance        - dry-run wallet balances
    GET  /api/v1/profit         - aggregate PnL / winrate / profit factor stats
    GET  /api/v1/performance    - per-pair performance breakdown
    GET  /api/v1/daily          - daily PnL series (used for the equity/PnL chart)
    GET  /api/v1/whitelist      - configured pairs
    GET  /api/v1/show_config    - active strategy name, timeframe, dry-run flag, etc.
    POST /api/v1/start          - resume the bot loop
    POST /api/v1/stop           - pause the bot loop

Endpoint paths/response shapes are reconstructed from Freqtrade's documented REST API and
should be verified against `/api/v1/version` + the live docs for whatever Freqtrade release is
actually deployed - see the version pin note in README.md.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config.logging_config import get_logger
from app.config.settings import get_settings

logger = get_logger("freqtrade_client")


class FreqtradeAuthError(RuntimeError):
    pass


class FreqtradeClient:
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.freqtrade_api_url.rstrip("/")
        self.username = settings.freqtrade_api_username
        self.password = settings.freqtrade_api_password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ---------------- Auth ----------------

    async def login(self) -> None:
        resp = await self._client.post(
            "/api/v1/token/login", auth=(self.username, self.password)
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        logger.info("authenticated with Freqtrade API at %s", self.base_url)

    async def _refresh(self) -> bool:
        if not self._refresh_token:
            return False
        resp = await self._client.post(
            "/api/v1/token/refresh",
            headers={"Authorization": f"Bearer {self._refresh_token}"},
        )
        if resp.status_code != 200:
            return False
        self._access_token = resp.json()["access_token"]
        return True

    async def _authed_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._access_token is None:
            await self.login()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        resp = await self._client.request(method, path, headers=headers, **kwargs)

        if resp.status_code == 401:
            if not await self._refresh():
                await self.login()
            headers["Authorization"] = f"Bearer {self._access_token}"
            resp = await self._client.request(method, path, headers=headers, **kwargs)

        resp.raise_for_status()
        return resp

    async def get(self, path: str) -> Any:
        resp = await self._authed_request("GET", path)
        return resp.json()

    async def post(self, path: str, json: dict | None = None) -> Any:
        resp = await self._authed_request("POST", path, json=json or {})
        return resp.json()

    # ---------------- Freqtrade endpoints (thin pass-through, no reinterpretation) ----------------

    async def ping(self) -> Any:
        resp = await self._client.get("/api/v1/ping")
        resp.raise_for_status()
        return resp.json()

    async def status(self) -> Any:
        return await self.get("/api/v1/status")

    async def trades(self, limit: int = 200) -> Any:
        return await self.get(f"/api/v1/trades?limit={limit}")

    async def balance(self) -> Any:
        return await self.get("/api/v1/balance")

    async def profit(self) -> Any:
        return await self.get("/api/v1/profit")

    async def performance(self) -> Any:
        return await self.get("/api/v1/performance")

    async def daily(self, days: int = 30) -> Any:
        return await self.get(f"/api/v1/daily?timescale={days}")

    async def whitelist(self) -> Any:
        return await self.get("/api/v1/whitelist")

    async def show_config(self) -> Any:
        return await self.get("/api/v1/show_config")

    async def start(self) -> Any:
        return await self.post("/api/v1/start")

    async def stop(self) -> Any:
        return await self.post("/api/v1/stop")

    async def access_token(self) -> str:
        if self._access_token is None:
            await self.login()
        return self._access_token


freqtrade_client = FreqtradeClient()
