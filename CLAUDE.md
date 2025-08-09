# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a NASDAQ stock signal bot that monitors the market for buy signals using the Kwon Strategy on weekly candlestick data. It filters stocks by market cap, analyzes patterns, and sends real-time notifications via Telegram. The bot is designed to run 24/7 on Render's starter plan.

## Common Development Commands

### Local Development
```bash
# Setup virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot locally
python stock_signal_bot.py

# Or use the convenience script
./run_local_stock.sh

# Run with web interface
./run_local_stock.sh --web
```

### Render Deployment
```bash
# Deploy to Render
./deploy_to_render.sh

# View logs (if using Render CLI)
render logs --tail
```

## Architecture and Key Components

### Core Strategy Flow
1. **Market Cap Filtering**: FMP API → Filter NASDAQ stocks by market cap range (500M-50B USD default)
2. **Symbol Validation**: Verify stocks meet volume and price criteria
3. **Pattern Analysis**: Fetch weekly candles → Apply Kwon Strategy
4. **Signal Generation**: Identify single peak + bearish pattern + EMA position
5. **Notification**: Send buy signals via Telegram with entry/TP/SL prices

### Module Structure
- **stock_signal_bot.py**: Main orchestrator, scheduling, error handling, Telegram integration
- **stocks.py**: FMP API integration, data fetching, batch processing
- **decision.py**: Kwon Strategy implementation adapted for stocks
- **indicators.py**: Technical indicators calculation (EMA)
- **config.py**: Configuration management, API credentials
- **fmp_api.py**: FMP API client with rate limiting and caching
- **render_web_wrapper.py**: Flask server wrapper for Render health checks

### API Integration Points
- **FMP (Financial Modeling Prep)**: Stock screening, historical data, quotes, company profiles
- **Telegram Bot API**: Message delivery for signals

### Error Handling Strategy
- Rate limit management (250/750 requests per day)
- Smart caching to minimize API calls
- Batch processing for memory efficiency
- Automatic retry with exponential backoff

## Environment Configuration

Required environment variables (set in .env file):
```bash
FMP_API_KEY           # FMP API key (required)
TELEGRAM_BOT_TOKEN    # Telegram bot token
TELEGRAM_CHAT_ID      # Telegram chat ID for notifications

# Optional parameters
TP_RATIO=0.07         # Take profit ratio (default: 7%)
SL_RATIO=0.03         # Stop loss ratio (default: 3%)
MIN_MARKET_CAP=500000000    # Min market cap filter
MAX_MARKET_CAP=50000000000  # Max market cap filter
SCAN_INTERVAL=3600    # Scan frequency in seconds
```

## Render Deployment Configuration
- **Memory**: 512MB (starter plan limit)
- **Plan**: Starter ($7/month)
- **Region**: Oregon (US West)
- **Health Check**: /health endpoint
- **Security**: Environment variables via Render dashboard

## Testing and Validation

Currently no automated tests are configured. Manual testing approach:
1. Check FMP API connectivity with small stock set
2. Verify Telegram notifications are received
3. Monitor logs for error patterns
4. Validate signal generation logic with known patterns

## Key Implementation Details

### Kwon Strategy for Stocks
The strategy looks for:
1. Single peak within last 10 weekly candles
2. Bearish pattern after the peak
3. Current low below EMA (20 or 50 period)
4. Entry at EMA price, TP at +7%, SL at -3%

### FMP API Rate Limit Management
- Free tier: 250 requests/day
- Starter: 750 requests/day
- Implements smart caching and batch processing
- Tracks daily usage and prevents exceeding limits

### Memory Optimization for Render
- Batch processing (20 stocks at a time)
- LRU caching with size limits
- Garbage collection after each batch
- Optimized for 512MB RAM constraint

### Scheduling
- Immediate scan on startup
- Hourly scans thereafter (configurable)
- Market hours awareness (optional)
- Daily status update at market close

## Important Notes

- NEVER exceed FMP API rate limits
- Always validate market hours before scanning
- Maintain memory usage under 400MB for safety
- Use watchlist mode for specific stock monitoring
- Cache aggressively to minimize API calls