"""
Thin proxy routes only. Every response here is Freqtrade's own JSON, forwarded as-is (or with
trivial reshaping for the dashboard's convenience) - no PnL/wallet/position math happens in
this file. That logic already lives in the Freqtrade process itself.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
import httpx

from app.freqtrade_client import freqtrade_client

router = APIRouter()


async def _proxy(coro):
    try:
        return await coro
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Freqtrade API unreachable: {exc}")


@router.get("/api/status")
async def api_status():
    return await _proxy(freqtrade_client.status())


@router.get("/api/trades")
async def api_trades(limit: int = 200):
    return await _proxy(freqtrade_client.trades(limit))


@router.get("/api/balance")
async def api_balance():
    return await _proxy(freqtrade_client.balance())


@router.get("/api/profit")
async def api_profit():
    return await _proxy(freqtrade_client.profit())


@router.get("/api/performance")
async def api_performance():
    return await _proxy(freqtrade_client.performance())


@router.get("/api/daily")
async def api_daily(days: int = 30):
    return await _proxy(freqtrade_client.daily(days))


@router.get("/api/whitelist")
async def api_whitelist():
    return await _proxy(freqtrade_client.whitelist())


@router.get("/api/fees")
async def api_fees():
    trades = await freqtrade_client.trades(limit=9999)
    trades_list = trades.get("trades") if isinstance(trades, dict) else trades
    total_fee = 0.0
    for t in trades_list:
        total_fee += t.get("fee_open_cost") or 0
        total_fee += t.get("fee_close_cost") or 0
    return {"total_fees": round(total_fee, 6), "avg_fee_per_trade": round(total_fee / max(len(trades_list), 1), 6), "trade_count": len(trades_list)}


@router.get("/api/config")
async def api_config():
    return await _proxy(freqtrade_client.show_config())


@router.post("/control/start")
async def control_start():
    return await _proxy(freqtrade_client.start())


@router.post("/control/stop")
async def control_stop():
    return await _proxy(freqtrade_client.stop())
