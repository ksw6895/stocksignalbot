#!/bin/bash

echo "==================================="
echo "Stock Signal Bot - Local Testing"
echo "==================================="

if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please create a .env file with required credentials"
    echo "Copy .env.example to .env and fill in your API keys"
    exit 1
fi

source .env

if [ -z "$FMP_API_KEY" ]; then
    echo "Error: FMP_API_KEY not set in .env"
    exit 1
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Error: TELEGRAM_BOT_TOKEN not set in .env"
    exit 1
fi

if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Error: TELEGRAM_CHAT_ID not set in .env"
    exit 1
fi

echo "✓ Environment variables loaded"
echo ""
echo "Configuration:"
echo "- Market Cap Range: $${MIN_MARKET_CAP:-500000000} - $${MAX_MARKET_CAP:-50000000000}"
echo "- TP Ratio: ${TP_RATIO:-7}%"
echo "- SL Ratio: ${SL_RATIO:-3}%"
echo "- Scan Interval: ${SCAN_INTERVAL:-3600} seconds"
echo "- Market Hours Only: ${SCAN_MARKET_HOURS_ONLY:-true}"
echo ""

if [ "$1" == "--web" ]; then
    echo "Starting with web interface on port ${PORT:-10000}..."
    python render_web_wrapper.py
else
    echo "Starting bot in standalone mode..."
    python stock_signal_bot.py
fi