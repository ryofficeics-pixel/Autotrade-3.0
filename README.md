# Paper Trading Dashboard (for Freqtrade dry-run)

**This project is a dashboard. It is not a trading engine.**

The paper trading engine is a real, unmodified Freqtrade process running
`freqtrade trade --dry-run`. Freqtrade's own dry-run mode already implements everything a
paper trading engine needs — wallet simulation, order fills, position tracking, PnL/Sharpe/
Sortino/profit-factor stats, and risk protections (`CooldownPeriod`, `MaxDrawdown`,
`StoplossGuard`) — via its own REST API server. This repo's only job is to sit in front of
that API and present it well.

**Freqtrade version targeted: `2024.9`** (only relevant to which REST endpoints/response
fields exist on the running instance — this repo has no Python dependency on Freqtrade at all).

## Architecture

```
freqtrade trade --dry-run           <- the actual paper trading engine (not our code)
  --config config/config.dryrun.json
  --strategy <YourStrategy>
        |
        | Freqtrade's own REST API (api_server.enabled: true)
        v
app/freqtrade_client.py             <- thin authenticated HTTP client (JWT login/refresh)
app/ws_relay.py                     <- relays Freqtrade's own WebSocket verbatim
app/dashboard/routes.py             <- thin proxy endpoints, no business logic
app/dashboard/static/index.html     <- the actual dashboard UI
```

Nothing under `app/` imports Freqtrade's Python package, computes indicators, simulates
orders, tracks a wallet, or calculates PnL. All of that is Freqtrade's own code, running as
its own process. If you find yourself wanting to add "smarter" logic here — re-deriving a
signal, recomputing PnL, tracking positions ourselves — that logic almost certainly already
exists in Freqtrade and belongs in `config/config.dryrun.json` or a real strategy file, not
in this repo.

## Run with Docker (recommended)

```bash
docker compose up --build
```

This starts two containers:
- `freqtrade` — the official `freqtradeorg/freqtrade:stable` image, dry-run mode, REST API
  enabled on port 8080, using `config/config.dryrun.json` and whatever strategy is in
  `strategies/`.
- `dashboard` — this repo, on port 8000.

Open `http://localhost:8000/`.

## Run locally (without Docker)

```bash
./setup.sh
# Terminal 1
freqtrade trade --config config/config.dryrun.json --strategy SampleStrategy --userdir .
# Terminal 2
source .venv/bin/activate
uvicorn app.main:app --reload
```

`setup.sh` scaffolds `strategies/SampleStrategy.py` by calling Freqtrade's own
`freqtrade new-strategy --template full` — that file is Freqtrade's generated example, not
ours. To run a real strategy (NostalgiaForInfinity, BBRSI, ElliotV7, MultiMA_TSL, ...), drop
its `.py` file into `strategies/` and change `--strategy` accordingly.

## Configuring the engine

Everything that used to be `.env` settings for a custom engine (stake sizing, max open trades,
risk limits, exchange, pairs) now lives in `config/config.dryrun.json`, because that's
Freqtrade's own config file for its own dry-run engine:

- `stake_amount`, `max_open_trades`, `dry_run_wallet` — position sizing / wallet
- `exchange.pair_whitelist` — pairs to trade
- `protections` — `CooldownPeriod`, `MaxDrawdown`, `StoplossGuard` (Freqtrade's real risk gates)
- `api_server` — must stay `enabled: true`; username/password must match `.env`'s
  `FREQTRADE_API_USERNAME`/`FREQTRADE_API_PASSWORD`

`.env` only configures the dashboard's *connection* to that API (`FREQTRADE_API_URL` and
credentials) — it configures nothing about trading itself.

## Dashboard endpoints (all thin proxies to Freqtrade's own API)

| Dashboard route | Freqtrade endpoint |
|---|---|
| `GET /api/status` | `GET /api/v1/status` (open trades) |
| `GET /api/trades` | `GET /api/v1/trades` (trade history) |
| `GET /api/balance` | `GET /api/v1/balance` |
| `GET /api/profit` | `GET /api/v1/profit` |
| `GET /api/performance` | `GET /api/v1/performance` |
| `GET /api/daily` | `GET /api/v1/daily` |
| `GET /api/whitelist` | `GET /api/v1/whitelist` |
| `GET /api/config` | `GET /api/v1/show_config` |
| `POST /control/start` | `POST /api/v1/start` |
| `POST /control/stop` | `POST /api/v1/stop` |
| `WS /ws/messages` | `WS /api/v1/message/ws` (relayed verbatim) |

These endpoint paths and response field names are reconstructed from Freqtrade's documented
REST API and have not been verified against a live running instance in this environment
(no network access here). Before relying on this in production, hit each endpoint once
against your actual Freqtrade instance and confirm field names match what
`app/dashboard/static/index.html`'s `pick(...)` fallbacks expect — the JS is written
defensively (multiple candidate field names) precisely because of this.

## Tests

```bash
pytest
```

Covers `FreqtradeClient`'s JWT login/refresh/retry behavior (the only logic this repo owns)
against a mocked transport — no real Freqtrade instance or network access required.

## What this repo deliberately does not do

- No indicator computation, signal generation, order simulation, wallet, or PnL math —
  that's Freqtrade's dry-run engine, unmodified.
- No custom database — Freqtrade has its own SQLite persistence.
- No "switch strategy live" control — Freqtrade doesn't expose that over REST; changing
  strategy means changing `--strategy` and restarting the process (or `reload_config` after
  editing the config, if you're only changing parameters).
