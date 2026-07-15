"""
Connects once to Freqtrade's own WebSocket (/api/v1/message/ws) and rebroadcasts every message
verbatim to any dashboard browser tabs connected to us. We do not parse or reinterpret message
content here - Freqtrade defines its own message schema (whitelist/analyzed_df/entry/exit
notifications); the dashboard's JS decides what to do with each message type.
"""
from __future__ import annotations

import asyncio
import json

import websockets
from fastapi import WebSocket

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.freqtrade_client import freqtrade_client

logger = get_logger("ws_relay")


class WSRelay:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task | None = None
        self._running = False

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def _broadcast(self, message: str) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def _upstream_loop(self) -> None:
        settings = get_settings()
        ws_url = settings.freqtrade_api_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        # Subscribe to all message types so the dashboard ticker/terminal gets everything
        subscribe_msg = json.dumps({
            "type": "subscribe",
            "data": [
                "status", "warning", "exception", "startup",
                "entry", "entry_fill", "entry_cancel",
                "exit", "exit_fill", "exit_cancel",
                "protection_trigger", "protection_trigger_global",
                "strategy_msg", "whitelist", "analyzed_df", "new_candle",
            ],
        })

        while self._running:
            try:
                token = await freqtrade_client.access_token()
                async with websockets.connect(
                    f"{ws_url}/api/v1/message/ws?token={token}",
                    ping_interval=20,
                ) as upstream:
                    logger.info("connected to Freqtrade websocket")
                    await upstream.send(subscribe_msg)
                    logger.info("subscribed to all message types")
                    async for message in upstream:
                        await self._broadcast(message if isinstance(message, str) else message.decode())
            except Exception:
                logger.exception("Freqtrade websocket connection dropped, retrying in 5s")
                await asyncio.sleep(5)

    def start(self) -> None:
        self._running = True
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._upstream_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()


ws_relay = WSRelay()
