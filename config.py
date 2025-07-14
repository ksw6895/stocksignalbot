import os
import logging
from dotenv import load_dotenv
from typing import List

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
CMC_API_KEY = os.getenv("COINMARKETCAP_API_KEY")  # <-- In .env

BASE_URL = "https://api.binance.com"
CMC_BASE_URL = "https://pro-api.coinmarketcap.com"
CMC_PAGE_SIZE = 5000

def load_filtered_symbols_from_file(filename: str = "filtered_coins.txt") -> List[str]:
    try:
        with open(filename, "r") as f:
            lines = f.read().splitlines()
        symbols = [line.strip() for line in lines if line.strip()]
        return symbols
    except Exception as e:
        logging.error(f"Error loading symbols from {filename}: {e}")
        return []
    
ANALYSIS_SYMBOLS: List[str] = load_filtered_symbols_from_file()
