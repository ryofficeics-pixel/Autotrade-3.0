#!/usr/bin/env bash
set -euo pipefail

# --- Dashboard (this repo's own code) ---
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example - edit FREQTRADE_API_* to match config/config.dryrun.json."
fi

# --- Freqtrade itself (the actual trading engine, not our code) ---
# Installed separately so the dashboard's own dependency set stays free of it.
if ! command -v freqtrade &> /dev/null; then
  pip install freqtrade
fi

mkdir -p strategies
if [ ! -f strategies/SampleStrategy.py ]; then
  freqtrade create-userdir --userdir user_data
  freqtrade new-strategy --userdir user_data --strategy SampleStrategy --template full
  cp user_data/strategies/SampleStrategy.py strategies/SampleStrategy.py
  echo "Generated strategies/SampleStrategy.py via 'freqtrade new-strategy' (Freqtrade's own scaffold)."
fi

echo ""
echo "Setup complete. Two processes to run, in separate terminals:"
echo "  1) freqtrade trade --config config/config.dryrun.json --strategy SampleStrategy --userdir ."
echo "  2) source .venv/bin/activate && uvicorn app.main:app --reload"
echo ""
echo "Or just: docker compose up --build"
