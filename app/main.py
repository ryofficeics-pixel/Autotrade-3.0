from __future__ import annotations

import asyncio
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
    
    # Start AI auto-reconnection task (checks models every 5 min)
    ai_task = None
    try:
        from ai.router.model_router import get_router
        from ai.api import update_auto_reconnect
        
        async def _ai_health_loop():
            RETRY_DELAYS = [5, 15, 30]  # seconds between retries
            CYCLE_SLEEP = 300  # 5 minutes between full cycles
            
            while True:
                router = get_router()
                
                for attempt, delay in enumerate(RETRY_DELAYS + [CYCLE_SLEEP]):
                    try:
                        result = await router.health_check()
                        healthy = result.get("healthy", False)
                        active_model = ""
                        for m in result.get("models_tested", []):
                            if m.get("success"):
                                active_model = m["model"]
                                break
                        update_auto_reconnect(healthy, active_model)
                        
                        if healthy:
                            logger.info(f"AI reconnect OK — {active_model} active")
                            break  # back to CYCLE_SLEEP
                        else:
                            remaining = len(RETRY_DELAYS) - attempt
                            logger.warning(f"AI reconnect attempt {attempt+1}/{len(RETRY_DELAYS)+1} FAILED — {remaining} retries left")
                            if attempt < len(RETRY_DELAYS):
                                await asyncio.sleep(delay)
                            else:
                                await asyncio.sleep(CYCLE_SLEEP)
                    except Exception as exc:
                        logger.debug(f"AI health check error: {exc}")
                        if attempt < len(RETRY_DELAYS):
                            await asyncio.sleep(delay)
                        else:
                            await asyncio.sleep(CYCLE_SLEEP)
        
        ai_task = asyncio.create_task(_ai_health_loop())
        logger.info("AI auto-reconnect task started (every 5 min)")
    except ImportError:
        logger.info("AI layer not available — skipping auto-reconnect")
    
    logger.info("dashboard startup complete")
    yield
    
    if ai_task:
        ai_task.cancel()
        try:
            await ai_task
        except asyncio.CancelledError:
            pass
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

# AI status endpoint (Autotrade-3.1-AI)
try:
    from ai.api import router as ai_router
    app.include_router(ai_router, tags=["ai"])
    logger.info("AI layer enabled")
except ImportError:
    logger.info("AI layer not available (missing dependencies or config)")


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
