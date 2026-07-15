from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config.logging_config import setup_logging, get_logger
from app.config.settings import get_settings
from app.dashboard.routes import router as dashboard_router
from app.freqtrade_client import freqtrade_client
from app.ws_relay import ws_relay

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger("app")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await freqtrade_client.login()
    except Exception:
        logger.exception("could not reach Freqtrade API at startup - will retry lazily on first request")
    ws_relay.start()
    logger.info("dashboard startup complete")
    yield
    await ws_relay.stop()
    await freqtrade_client.close()
    logger.info("dashboard shutdown complete")


app = FastAPI(title="Paper Trading Dashboard", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router, tags=["dashboard"])


@app.get("/health")
async def health():
    try:
        await freqtrade_client.ping()
        return {"status": "ok", "freqtrade": "reachable"}
    except Exception as exc:
        return {"status": "degraded", "freqtrade": "unreachable", "detail": str(exc)}


@app.websocket("/ws/messages")
async def ws_messages(websocket: WebSocket):
    await ws_relay.register(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive / ignore client pings
    except WebSocketDisconnect:
        ws_relay.unregister(websocket)


@app.get("/{filename:path}")
async def static_files(filename: str):
    filepath = os.path.join(STATIC_DIR, filename)
    if os.path.isfile(filepath):
        return FileResponse(filepath)
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
