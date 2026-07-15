"""Patch Freqtrade exchange to use static market & OHLCV data (offline mode)."""
import json
from pathlib import Path

STATIC_MARKETS = {
    "BTC/USDT": {
        "id": "BTCUSDT", "symbol": "BTC/USDT", "base": "BTC", "quote": "USDT",
        "baseId": "BTC", "quoteId": "USDT", "active": True,
        "precision": {"price": 0.01, "amount": 0.00001, "cost": 0.01},
        "limits": {"amount": {"min": 0.0001, "max": 9000}, "price": {"min": 0.01, "max": 1000000}, "cost": {"min": 10, "max": 90000000}},
        "info": {"symbol": "BTCUSDT", "status": "TRADING"},
        "type": "spot", "spot": True, "swap": False, "future": False, "option": False,
        "linear": None, "inverse": None, "margin": True, "contract": False,
        "taker": 0.001, "maker": 0.001, "fee": 0.001,
    },
    "ETH/USDT": {
        "id": "ETHUSDT", "symbol": "ETH/USDT", "base": "ETH", "quote": "USDT",
        "baseId": "ETH", "quoteId": "USDT", "active": True,
        "precision": {"price": 0.01, "amount": 0.00001, "cost": 0.01},
        "limits": {"amount": {"min": 0.001, "max": 9000}, "price": {"min": 0.01, "max": 1000000}, "cost": {"min": 10, "max": 90000000}},
        "info": {"symbol": "ETHUSDT", "status": "TRADING"},
        "type": "spot", "spot": True, "swap": False, "future": False, "option": False,
        "linear": None, "inverse": None, "margin": True, "contract": False,
        "taker": 0.001, "maker": 0.001, "fee": 0.001,
    },
    "XRP/USDT": {
        "id": "XRPUSDT", "symbol": "XRP/USDT", "base": "XRP", "quote": "USDT",
        "baseId": "XRP", "quoteId": "USDT", "active": True,
        "precision": {"price": 0.0001, "amount": 0.1, "cost": 0.001},
        "limits": {"amount": {"min": 1, "max": 9000000}, "price": {"min": 0.0001, "max": 1000}, "cost": {"min": 1, "max": 90000000}},
        "info": {"symbol": "XRPUSDT", "status": "TRADING"},
        "type": "spot", "spot": True, "swap": False, "future": False, "option": False,
        "linear": None, "inverse": None, "margin": True, "contract": False,
        "taker": 0.001, "maker": 0.001, "fee": 0.001,
    },
    "DOGE/USDT": {
        "id": "DOGEUSDT", "symbol": "DOGE/USDT", "base": "DOGE", "quote": "USDT",
        "baseId": "DOGE", "quoteId": "USDT", "active": True,
        "precision": {"price": 0.00001, "amount": 1, "cost": 0.00001},
        "limits": {"amount": {"min": 1, "max": 9000000}, "price": {"min": 0.00001, "max": 1000}, "cost": {"min": 1, "max": 90000000}},
        "info": {"symbol": "DOGEUSDT", "status": "TRADING"},
        "type": "spot", "spot": True, "swap": False, "future": False, "option": False,
        "linear": None, "inverse": None, "margin": True, "contract": False,
        "taker": 0.001, "maker": 0.001, "fee": 0.001,
    },
    "SOL/USDT": {
        "id": "SOLUSDT", "symbol": "SOL/USDT", "base": "SOL", "quote": "USDT",
        "baseId": "SOL", "quoteId": "USDT", "active": True,
        "precision": {"price": 0.01, "amount": 0.01, "cost": 0.001},
        "limits": {"amount": {"min": 0.01, "max": 900000}, "price": {"min": 0.01, "max": 1000000}, "cost": {"min": 1, "max": 90000000}},
        "info": {"symbol": "SOLUSDT", "status": "TRADING"},
        "type": "spot", "spot": True, "swap": False, "future": False, "option": False,
        "linear": None, "inverse": None, "margin": True, "contract": False,
        "taker": 0.001, "maker": 0.001, "fee": 0.001,
    },
}

_HERE = Path(__file__).parent
_CACHE = {}


def _load_cached_data(pair: str, timeframe: str):
    key = f"{pair}-{timeframe}"
    if key not in _CACHE:
        safe_pair = pair.replace("/", "_")
        path = _HERE / "data" / "binance" / f"{safe_pair}-{timeframe}.json"
        if path.exists():
            with open(path) as f:
                _CACHE[key] = json.load(f)
        else:
            _CACHE[key] = []
    return _CACHE[key]


def _apply_markets(api):
    api.markets = {k: dict(v) for k, v in STATIC_MARKETS.items()}
    api.markets_by_id = {}
    for s, m in api.markets.items():
        api.markets_by_id[m["id"]] = m
    api.markets_in_chain = {}


def patch():
    import ccxt as ccxt_mod
    import freqtrade.exchange.exchange as ex_mod
    import copy

    # ---- Patch ccxt.binance (sync) ----
    orig_binance_init = ccxt_mod.binance.__init__
    def _patched_binance_init(self, config=None):
        orig_binance_init(self, config or {})
        _apply_markets(self)
        self.load_markets = lambda reload=False, *a, **kw: self.markets
    ccxt_mod.binance.__init__ = _patched_binance_init

    # ---- Patch ccxt.pro.binance (async WebSocket) ----
    try:
        from ccxt.pro.binance import binance as pro_binance
        orig_pro_init = pro_binance.__init__
        def _patched_pro_init(self, config=None):
            orig_pro_init(self, config or {})
            _apply_markets(self)
            self.load_markets = lambda reload=False, *a, **kw: self.markets
        pro_binance.__init__ = _patched_pro_init
    except Exception as e:
        pass

    # ---- Patch Exchange.reload_markets ----
    def _patched_reload_markets(self, *args, **kwargs):
        _apply_markets(self._api)
        self._api_async = copy.deepcopy(self._api)
        self._api_async.load_markets = lambda reload=False, *a, **kw: self._api_async.markets
        self._markets = self._api_async.markets
        try:
            self._api.set_markets_from_exchange(self._api_async)
        except Exception:
            pass
        self._api.options = self._api_async.options
        from freqtrade.enums import TradingMode
        try:
            if kwargs.get("load_leverage_tiers", True) and self.trading_mode == TradingMode.FUTURES:
                self.fill_leverage_tiers()
        except Exception:
            pass
        self._last_markets_refresh = 1

    ex_mod.Exchange.reload_markets = _patched_reload_markets

    # ---- Patch _async_get_candle_history to return mock data with live-like tail ----
    import time as time_mod

    async def _patched_get_candle_history(self, pair, timeframe, candle_type, since_ms=None):
        logger = getattr(self, 'logger', None)
        if logger:
            logger.info(f"PATCH: _async_get_candle_history called for {pair} {timeframe} since={since_ms}")
        candles = _load_cached_data(pair, timeframe)
        if not candles:
            if logger:
                logger.warning(f"PATCH: No cached data for {pair}")
            return (
                pair,
                timeframe,
                candle_type,
                [],
                self._ohlcv_partial_candle,
            )
        last_ts = candles[-1][0]
        now_ms = int(time_mod.time() * 1000)
        extended = list(candles)
        while last_ts < now_ms:
            last_ts += 300000
            if last_ts > now_ms:
                break
            prev = extended[-1]
            new_close = prev[4] * (1 + (0.5 - (last_ts % 11) / 11) * 0.002)
            new_candle = [
                last_ts,
                round(prev[4], 2),
                round(max(prev[4], new_close) * 1.001, 2),
                round(min(prev[4], new_close) * 0.999, 2),
                round(new_close, 2),
                round(prev[5] * (0.9 + (last_ts % 5) / 10), 4),
            ]
            extended.append(new_candle)
        if since_ms is not None:
            extended = [c for c in extended if c[0] >= since_ms]
        if logger:
            logger.info(f"PATCH: Returning {len(extended)} candles for {pair} (since filter: {since_ms is not None})")
        return (
            pair,
            timeframe,
            candle_type,
            extended,
            self._ohlcv_partial_candle,
        )

    orig_get_candle_history = ex_mod.Exchange._async_get_candle_history
    ex_mod.Exchange._async_get_candle_history = _patched_get_candle_history

    # ---- Tick-level price variation helpers ----
    import math

    def _live_price(pair: str) -> float:
        """Return base price (latest candle close) with a deterministic offset
        based on wall-clock time so the dashboard sees movement on every tick.
        Amplitude is enough to eventually trigger 1% take-profit or -5% stoploss."""
        candles = _load_cached_data(pair, "5m")
        base = candles[-1][4] if candles else (60000.0 if "BTC" in pair else 3000.0)
        now_s = time_mod.time()
        # fast tick ±0.05%, slow drift ±3% over ~30 min cycle
        tick = math.sin(now_s * 2.0) * 0.0005 + math.sin(now_s * 0.015) * 0.03
        return round(base * (1.0 + tick), 2)

    # ---- Patch fetch_l2_order_book to return mock data (avoids RequestTimeout) ----
    orig_order_book = ex_mod.Exchange.fetch_l2_order_book
    def _patched_fetch_order_book(self, pair: str, limit: int | None = None, *args, **kwargs):
        bid = _live_price(pair) * 0.999
        ask = _live_price(pair) * 1.001
        return {
            "bids": [[bid, 1.0], [bid * 0.999, 2.0]],
            "asks": [[ask, 1.0], [ask * 1.001, 2.0]],
            "timestamp": int(time_mod.time() * 1000),
        }
    ex_mod.Exchange.fetch_l2_order_book = _patched_fetch_order_book

    # ---- Patch get_tickers to return mock price data ----
    orig_ticker = ex_mod.Exchange.get_tickers
    def _patched_get_tickers(self, pair: str | None = None, *args, **kwargs):
        target_pairs = [pair] if pair else list(STATIC_MARKETS.keys())
        result = {}
        for p in target_pairs:
            price = _live_price(p)
            result[p] = {
                "symbol": p, "bid": price * 0.999, "ask": price * 1.001,
                "last": price, "baseVolume": 1000.0, "quoteVolume": price * 1000,
                "percentage": 0.1,
            }
        return result if pair is None else result.get(pair, {})
    ex_mod.Exchange.get_tickers = _patched_get_tickers

    # ---- Patch fetch_ticker to return mock data (avoid RequestTimeout) ----
    orig_fetch_ticker = ex_mod.Exchange.fetch_ticker
    def _patched_fetch_ticker(self, pair: str, *args, **kwargs):
        price = _live_price(pair)
        return {
            "symbol": pair, "bid": price * 0.999, "ask": price * 1.001,
            "last": price, "baseVolume": 1000.0, "quoteVolume": price * 1000,
            "percentage": 0.1, "high": price * 1.01, "low": price * 0.99,
            "open": price, "close": price, "previousClose": price * 0.997,
            "change": price * 0.002, "average": price, "vwap": price,
        }
    ex_mod.Exchange.fetch_ticker = _patched_fetch_ticker



    # ---- Silence exchange WS errors by patching the watch method to return mock data ----
    try:
        from freqtrade.exchange.exchange_ws import ExchangeWS
        orig_watch = ExchangeWS._continuously_async_watch_ohlcv
        async def _patched_watch(self, *args, **kwargs):
            import asyncio
            while True:
                await asyncio.sleep(60)
        ExchangeWS._continuously_async_watch_ohlcv = _patched_watch
    except Exception:
        pass
