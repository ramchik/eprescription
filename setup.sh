#!/usr/bin/env bash
# One-time setup for the ePrescription automation tool

set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing Playwright browsers..."
playwright install chromium

if [ ! -f .env ]; then
  echo "==> Creating .env from template..."
  cp .env.example .env
  echo ""
  echo "  *** Edit .env and add your credentials before running the app ***"
fi

echo ""
echo "Setup complete!"
echo "  1. Edit .env with your username/password"
echo "  2. Edit config.yaml if you need to adjust form selectors"
echo "  3. Run:  python app.py"
echo "  4. Open: http://localhost:5000"
