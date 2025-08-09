import os
import logging
from dotenv import load_dotenv
from typing import List

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FMP_BASE_URL = "https://financialmodelingprep.com/api"

MIN_MARKET_CAP = int(os.getenv("MIN_MARKET_CAP", "500000000"))
MAX_MARKET_CAP = int(os.getenv("MAX_MARKET_CAP", "50000000000"))

TP_RATIO = float(os.getenv("TP_RATIO", "0.07"))
SL_RATIO = float(os.getenv("SL_RATIO", "0.03"))

SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "3600"))
SCAN_DURING_MARKET_HOURS_ONLY = os.getenv("SCAN_MARKET_HOURS_ONLY", "true").lower() == "true"

FMP_DAILY_LIMIT = int(os.getenv("FMP_DAILY_LIMIT", "250"))

EMA_SHORT_PERIOD = int(os.getenv("EMA_SHORT_PERIOD", "20"))
EMA_LONG_PERIOD = int(os.getenv("EMA_LONG_PERIOD", "50"))

MIN_VOLUME = int(os.getenv("MIN_VOLUME", "100000"))
MIN_PRICE = float(os.getenv("MIN_PRICE", "5.0"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "500.0"))

CACHE_DURATION = int(os.getenv("CACHE_DURATION", "3600"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))

RENDER_PORT = int(os.getenv("PORT", "10000"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def validate_config():
    errors = []
    
    if not FMP_API_KEY:
        errors.append("FMP_API_KEY is required")
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is required")
    
    if not TELEGRAM_CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID is required")
    
    if MIN_MARKET_CAP >= MAX_MARKET_CAP:
        errors.append("MIN_MARKET_CAP must be less than MAX_MARKET_CAP")
    
    if TP_RATIO <= 0 or TP_RATIO > 0.5:
        errors.append("TP_RATIO must be between 0 and 0.5")
    
    if SL_RATIO <= 0 or SL_RATIO > 0.2:
        errors.append("SL_RATIO must be between 0 and 0.2")
    
    if errors:
        for error in errors:
            logging.error(f"Config validation error: {error}")
        raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    logging.info("Configuration validated successfully")

def load_watchlist(filename: str = "watchlist.txt") -> List[str]:
    try:
        with open(filename, "r") as f:
            lines = f.read().splitlines()
        symbols = [line.strip().upper() for line in lines if line.strip() and not line.startswith("#")]
        logging.info(f"Loaded {len(symbols)} symbols from watchlist")
        return symbols
    except FileNotFoundError:
        logging.info("No watchlist file found, will scan all NASDAQ stocks")
        return []

WATCHLIST_SYMBOLS: List[str] = load_watchlist()

EXCLUDED_SYMBOLS = [
    "GOOG",
    "META",
]

def format_number(num: float) -> str:
    if num >= 1_000_000_000:
        return f"${num/1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"${num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"${num/1_000:.1f}K"
    else:
        return f"${num:.2f}"