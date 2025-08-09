# Stock Signal Bot - NASDAQ Scanner

A sophisticated stock market signal bot that monitors NASDAQ stocks for buy opportunities using the Kwon Strategy. Optimized for deployment on Render's starter plan.

## Features

- 📊 **NASDAQ Stock Scanning**: Monitors stocks within customizable market cap range
- 📈 **Kwon Strategy**: Advanced pattern recognition on weekly candles
- 🎯 **Smart Filtering**: Market cap, volume, and price filters
- 📱 **Telegram Notifications**: Real-time buy signals with entry/exit points
- 🌐 **Render Deployment**: Optimized for 512MB RAM constraint
- 📉 **FMP API Integration**: Comprehensive stock market data
- ⚡ **Memory Efficient**: Batch processing and smart caching
- 🕐 **Market Hours Aware**: Scans only during trading hours

## Quick Start

### Prerequisites

1. **FMP API Key**: Sign up at [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs)
   - Free tier: 250 requests/day
   - Starter: 750 requests/day ($14/month)

2. **Telegram Bot**: 
   - Create bot via [@BotFather](https://t.me/botfather)
   - Get your chat ID

3. **Python 3.11+**: Required for running locally

### Local Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd cryptosignal-1

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.stock.example .env
# Edit .env with your API keys

# Run the bot
./run_local_stock.sh

# Or with web interface
./run_local_stock.sh --web
```

## Render Deployment

### Automatic Deployment (Recommended)

1. Push code to GitHub/GitLab
2. Connect repository to Render
3. Render will auto-detect `render.yaml`
4. Add environment variables in Render dashboard
5. Deploy!

### Manual Deployment

```bash
# Run deployment helper
./deploy_to_render.sh

# Follow the interactive guide
```

### Render Configuration

- **Plan**: Starter ($7/month)
- **Region**: Oregon (US West)
- **Memory**: 512MB
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python render_web_wrapper.py`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FMP_API_KEY` | FMP API key (required) | - |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (required) | - |
| `TELEGRAM_CHAT_ID` | Telegram chat ID (required) | - |
| `MIN_MARKET_CAP` | Minimum market cap filter | $500M |
| `MAX_MARKET_CAP` | Maximum market cap filter | $50B |
| `TP_RATIO` | Take profit percentage | 7% |
| `SL_RATIO` | Stop loss percentage | 3% |
| `SCAN_INTERVAL` | Scan frequency in seconds | 3600 |
| `SCAN_MARKET_HOURS_ONLY` | Only scan during market hours | true |

### Watchlist Mode

Create `watchlist.txt` to monitor specific stocks:

```
AAPL
MSFT
GOOGL
# Comments supported
TSLA
```

## Strategy Details

### Kwon Strategy for Stocks

The bot identifies potential reversal patterns:

1. **Peak Detection**: Single peak in recent 10 weeks
2. **Bearish Confirmation**: Bearish candles after peak
3. **EMA Support**: Current price near EMA(20) or EMA(50)
4. **Volume Analysis**: Above-average volume preferred
5. **Risk Management**: Automatic TP/SL calculation

### Signal Criteria

- Peak formed 2-7 weeks ago
- Price pullback 10-30% from peak
- Current low below EMA
- Risk/Reward ratio > 1.5
- Volume ratio > 0.5x average

## API Endpoints (Web Mode)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Detailed bot status |
| `/metrics` | GET | Prometheus metrics |
| `/trigger-scan` | POST | Manual scan trigger |
| `/clear-cache` | POST | Clear data cache |

## API Rate Limits

### FMP Free Tier (250 requests/day)
- ~10-12 full scans per day
- Monitor 50-100 stocks effectively

### FMP Starter ($14/month, 750 requests/day)
- ~30-35 full scans per day
- Monitor 200+ stocks effectively

## Memory Optimization

The bot is optimized for Render's 512MB limit:

- Batch processing (20 stocks at a time)
- Incremental garbage collection
- LRU caching with size limits
- Streaming JSON parsing
- Automatic cache cleanup

## Monitoring

### Telegram Commands
The bot sends:
- Startup confirmation
- Buy signals with full analysis
- Daily summary at market close
- Error notifications

### Web Dashboard
Access at `https://your-app.onrender.com/status`:
- Current scan status
- API requests remaining
- Memory usage
- Signal history

## Troubleshooting

### Common Issues

1. **High Memory Usage**
   - Reduce `BATCH_SIZE`
   - Lower cache duration
   - Limit market cap range

2. **API Rate Limits**
   - Increase `SCAN_INTERVAL`
   - Use watchlist mode
   - Upgrade FMP plan

3. **No Signals**
   - Check market conditions
   - Verify strategy parameters
   - Review filtered stocks

### Logs

```bash
# View Render logs
render logs --tail

# Local debugging
LOG_LEVEL=DEBUG ./run_local_stock.sh
```

## Development

### Project Structure

```
├── fmp_api.py           # FMP API client
├── config_stock.py      # Configuration
├── stocks.py            # Stock data fetching
├── decision_stock.py    # Kwon strategy
├── indicators.py        # Technical indicators
├── stock_signal_bot.py  # Main bot logic
├── render_web_wrapper.py # Web server
├── render.yaml          # Render config
└── requirements.txt     # Dependencies
```

### Testing Locally

```python
# Test FMP connection
python -c "from fmp_api import FMPAPIClient; client = FMPAPIClient('YOUR_KEY'); print(client.is_market_open())"

# Test strategy
python -c "from stocks import StockDataFetcher; fetcher = StockDataFetcher(); print(fetcher.get_filtered_stocks()[:5])"
```

## License

MIT License - See LICENSE file

## Support

- Create an issue on GitHub
- Check logs for error details
- Verify API keys and limits

## Disclaimer

This bot is for educational purposes only. Always do your own research before making investment decisions. Past performance does not guarantee future results.