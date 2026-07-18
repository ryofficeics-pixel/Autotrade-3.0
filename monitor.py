"""Audit loop. Runs performance audit every 30 min and logs to CSV."""
from __future__ import annotations

import base64
import csv
import json
import os
import time
import urllib.request
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "monitor_log.csv")
API_HOST = "http://127.0.0.1:8080"
CREDS = base64.b64encode(b"freqtrader:changeme").decode()


def _token():
    req = urllib.request.Request(API_HOST + "/api/v1/token/login", data=b"", method="POST")
    req.add_header("Authorization", "Basic " + CREDS)
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def ft(path):
    r = urllib.request.Request(API_HOST + path)
    r.add_header("Authorization", "Bearer " + _token())
    return json.loads(urllib.request.urlopen(r).read())


def audit():
    p = ft("/api/v1/profit")
    status = ft("/api/v1/status")
    trades = ft("/api/v1/trades?limit=200")
    perf = ft("/api/v1/performance")

    closed = p["closed_trade_count"]
    winrate = p["winrate"] or 0
    net_pnl = p["profit_closed_coin"]

    total_fees = 0
    total_gross = 0
    winners = 0
    losers = 0
    win_net_total = 0.0
    lose_net_total = 0.0

    for tr in trades.get("trades", []):
        gross = tr["close_rate"] * tr["amount"] - tr["open_rate"] * tr["amount"]
        fees = (tr.get("fee_open_cost") or 0) + (tr.get("fee_close_cost") or 0)
        _net = tr["profit_abs"]
        total_fees += fees
        total_gross += gross
        if _net > 0:
            winners += 1
            win_net_total += _net
        else:
            losers += 1
            lose_net_total += _net

    fee_pct_of_gross = (total_fees / total_gross * 100) if total_gross else 0
    avg_win = win_net_total / max(winners, 1)
    avg_lose = abs(lose_net_total) / max(losers, 1)
    rrr = avg_win / max(avg_lose, 0.001)

    # Pair ranking by profitability
    ranked_pairs = sorted(
        (p for p in perf if p.get("profit_abs") is not None),
        key=lambda x: x["profit_abs"],
        reverse=True,
    )
    best_pair = ranked_pairs[0] if ranked_pairs else {}
    worst_pair = ranked_pairs[-1] if ranked_pairs else {}

    # Check AI status
    ai_info = {}
    try:
        r2 = urllib.request.Request("http://127.0.0.1:8000/api/ai/status")
        import socket
        socket.setdefaulttimeout(5)
        ai_info = json.loads(urllib.request.urlopen(r2, timeout=5).read())
    except Exception:
        ai_info = {"enabled": False, "mode": "legacy"}

    result = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trades": closed,
        "open": len(status),
        "winrate": round(winrate * 100, 1),
        "net_pnl": round(net_pnl, 4),
        "gross_pnl": round(total_gross, 4),
        "total_fees": round(total_fees, 4),
        "fee_pct_gross": round(fee_pct_of_gross, 1),
        "winners": winners,
        "losers": losers,
        "avg_win": round(avg_win, 4),
        "avg_lose": round(avg_lose, 4),
        "rrr": round(rrr, 2),
        "pairs": list({tr["pair"] for tr in trades.get("trades", [])}),
        # Pair rankings
        "best_pair": best_pair.get("pair", ""),
        "best_pnl": round(best_pair.get("profit_abs", 0), 4) if best_pair else 0,
        "best_trades": best_pair.get("count", 0),
        "worst_pair": worst_pair.get("pair", ""),
        "worst_pnl": round(worst_pair.get("profit_abs", 0), 4) if worst_pair else 0,
        "worst_trades": worst_pair.get("count", 0),
        # AI status
        "ai_enabled": ai_info.get("enabled", False),
        "ai_mode": ai_info.get("mode", "legacy"),
    }
    return result, ranked_pairs


def log_result(r):
    was_empty = not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if was_empty:
            w.writerow(r.keys())
        w.writerow(r.values())
    print(f"  logged to {LOG_FILE}")


def main():
    print(f"[{datetime.now().strftime('%H:%M')}] monitor.py started — audits every 30 min")

    while True:
        r, ranked_pairs = audit()
        ai_tag = f"AI={r['ai_mode']}" if r["ai_enabled"] else "AI=off"
        print(
            f"\n[{r['ts']}] {ai_tag} | {r['trades']} trades, {r['winrate']}% WR, "
            f"${r['net_pnl']} net, fee {r['fee_pct_gross']}% of gross"
        )

        # Show pair ranking
        print(f"  -- PAIR RANKING --")
        for rank, pair in enumerate(ranked_pairs[:5], 1):
            sign = "+" if pair["profit_abs"] >= 0 else ""
            print(f"  #{rank} {pair['pair']}: {sign}${pair['profit_abs']:.2f} ({pair['profit_pct']:.1f}%) "
                  f"in {pair['count']} trades")
        if ranked_pairs:
            worst = ranked_pairs[-1]
            print(f"  -- Best: {r['best_pair']} (${r['best_pnl']}) / "
                  f"Worst: {r['worst_pair']} (${r['worst_pnl']})")

        log_result(r)
        print(f"  next audit in 30 min...")
        time.sleep(1800)


if __name__ == "__main__":
    main()
