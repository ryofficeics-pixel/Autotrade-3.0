"""Generate mock OHLCV data for offline mode."""
import json
import time
import os
import shutil

PAIRS = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "DOGE/USDT", "SOL/USDT"]
TIMEFRAME = "5m"
SINCE = int(time.time()) - 86400 * 7  # 7 days ago
INTERVAL = 300  # 5 minutes in seconds

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "binance")


def generate_candles(pair, count=2016):
    candles = []
    base_price = (
        60000 if "BTC" in pair else
        3000 if "ETH" in pair else
        150 if "SOL" in pair else
        2 if "XRP" in pair else
        0.2
    )
    ts = SINCE
    for i in range(count):
        volatility = base_price * 0.02
        trend = base_price * 0.00001
        open_p = base_price + (i * trend) + (volatility * (0.5 - (i % 100) / 100))
        close_p = open_p + volatility * (0.5 - (i % 7) / 7)
        high_p = max(open_p, close_p) + volatility * 0.3
        low_p = min(open_p, close_p) - volatility * 0.3
        volume = 100 + (i % 50)
        candles.append([int(ts * 1000), round(open_p, 2), round(high_p, 2), round(low_p, 2), round(close_p, 2), round(volume, 4)])
        ts += INTERVAL
    return candles


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for pair in PAIRS:
        safe_pair = pair.replace("/", "_")
        filename = f"{safe_pair}-{TIMEFRAME}.json"
        filepath = os.path.join(DATA_DIR, filename)
        candles = generate_candles(pair)
        with open(filepath, "w") as f:
            json.dump(candles, f)
        print(f"Created {filepath} with {len(candles)} candles")
    print("Done seeding data.")


if __name__ == "__main__":
    main()
