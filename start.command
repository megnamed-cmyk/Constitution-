#!/usr/bin/env bash
# Constitutional Analysis Engine: one-click start for macOS / Linux.
# First run installs everything (several minutes); later runs start in seconds.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf "\n==> %s\n" "$1"; }
die() { printf "\nERROR: %s\n" "$1"; read -r -p "Press Enter to close..." _; exit 1; }

command -v python3 >/dev/null || die "Python 3.10+ is required. Install it from https://www.python.org/downloads/"
command -v npm >/dev/null || die "Node.js is required. Install the LTS version from https://nodejs.org/"

if [ ! -f .env ]; then
  say "One-time setup: your Claude API key (from https://console.anthropic.com/settings/keys)"
  read -r -p "Paste ANTHROPIC_API_KEY: " key
  printf "ANTHROPIC_API_KEY=%s\n" "$key" > .env
  chmod 600 .env
fi
set -a; . ./.env; set +a

if [ ! -x .venv/bin/python ]; then
  say "Installing Python packages (first run only, can take 5-10 minutes)"
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r backend/requirements.txt
fi

if [ ! -d backend/data/constitutional_db ]; then
  say "Building the knowledge base (first run only)"
  (cd backend && ../.venv/bin/python -m ingest seed)
  (cd backend && ../.venv/bin/python -m ingest constitution) || echo "  Warning: couldn't load the Constitution text; continuing with demo data."
  read -r -p "Also download the full Constitution Annotated now? This takes a long time. [y/N] " ans
  if [[ "${ans:-n}" =~ ^[Yy] ]]; then
    (cd backend && ../.venv/bin/python -m ingest conan) || echo "  Warning: CONAN download stopped early; rerun later with: cd backend && ../.venv/bin/python -m ingest conan"
  fi
fi

if [ ! -d frontend/node_modules ]; then
  say "Installing web app packages (first run only)"
  (cd frontend && npm install --no-audit --no-fund)
fi

say "Starting. The app opens at http://localhost:5173. Close this window to stop."
(cd backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
(sleep 4; (command -v open >/dev/null && open http://localhost:5173) || (command -v xdg-open >/dev/null && xdg-open http://localhost:5173) || true) &
cd frontend && npm run dev
