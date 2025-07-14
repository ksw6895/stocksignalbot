import logging
import requests
import time
import sys
import pandas as pd
from typing import List, Optional
from config import BASE_URL, CMC_PAGE_SIZE, CMC_API_KEY, CMC_BASE_URL, load_filtered_symbols_from_file
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException

###############################################################################
# HELPER: EXPONENTIAL RETRY WRAPPER
###############################################################################
def retry_request(
    url: str,
    method: str = "GET",
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: int = 20,
    max_retries: int = 5
):
    attempt = 0
    while attempt < max_retries:
        try:
            if method.upper() == "GET":
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            else:
                resp = requests.post(url, data=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except (ConnectTimeout, ReadTimeout, RequestException) as e:
            logging.error(f"Request error on attempt {attempt+1} for {url}: {e}")
            time.sleep(2 ** attempt)
            attempt += 1
    logging.error(f"Max retries ({max_retries}) reached for {url}.")
    return None

###############################################################################
# FETCH MULTIPLE PAGES FROM COINMARKETCAP
###############################################################################
def fetch_coinmarketcap_coins_multi_pages(
    min_cap: float = 200_000_000, 
    max_cap: float = 20_000_000_000,
    max_pages: int = 4
) -> List[dict]:
    all_coins = []
    logging.info(f"Fetching up to {max_pages} pages from CoinMarketCap, sir...")

    for page_index in range(max_pages):
        start_val = page_index * CMC_PAGE_SIZE + 1
        logging.info(f"Fetching page {page_index+1}, start={start_val}...")
        url = f"{CMC_BASE_URL}/v1/cryptocurrency/listings/latest"
        params = {
            "start": str(start_val),
            "limit": str(CMC_PAGE_SIZE),
            "convert": "USD"
        }
        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": CMC_API_KEY
        }

        resp = retry_request(url, method="GET", params=params, headers=headers, timeout=30)
        if resp is None:
            logging.warning(f"Could not get page {page_index+1}, stopping.")
            break
        
        data = resp.json()
        page_coins = data.get("data", [])
        if not page_coins:
            logging.info("Empty data returned — no more coins, sir.")
            break
        all_coins.extend(page_coins)

        if len(page_coins) < CMC_PAGE_SIZE:
            logging.info("Reached last partial page, sir.")
            break

    matched = []
    for coin in all_coins:
        try:
            cap = coin["quote"]["USD"]["market_cap"]
        except KeyError:
            continue
        if cap is not None and min_cap <= cap <= max_cap:
            matched.append(coin)

    logging.info(f"Total coins fetched: {len(all_coins)}. Filtered down to: {len(matched)}.")
    return matched

###############################################################################
# SAVE FILTERED SYMBOLS TO FILE
###############################################################################
def save_filtered_symbols_to_file(symbols: List[str], filename: str = "filtered_coins.txt"):
    try:
        with open(filename, "w") as f:
            for sym in symbols:
                f.write(sym + "\n")
        logging.info(f"Filtered symbols saved to {filename}, sir.")
    except Exception as e:
        logging.error(f"Error saving symbols to {filename}: {e}")

###############################################################################
# GET VALID BINANCE SYMBOLS
###############################################################################
def get_valid_binance_symbols() -> set:
    endpoint = f"{BASE_URL}/api/v3/exchangeInfo"
    resp = retry_request(endpoint, method="GET", params={}, timeout=20, max_retries=5)
    if resp is None:
        logging.error("Failed to fetch Binance exchange info, sir.")
        return set()
    try:
        data = resp.json()
        symbols_data = data.get("symbols", [])
        valid_symbols = set()
        for s in symbols_data:
            if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
                valid_symbols.add(s.get("symbol"))
        return valid_symbols
    except Exception as e:
        logging.error(f"Error parsing exchange info: {e}")
        return set()

###############################################################################
# INITIALIZE SYMBOLS
###############################################################################
def initialize_symbols() -> List[str]:
    print("Please choose an option, sir:")
    print("1: Filter by market capitalization using CoinMarketCap (multi-page) and save the result.")
    print("2: Import existing filtered coin list from file.")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        coins = fetch_coinmarketcap_coins_multi_pages(
            min_cap=150_000_000, 
            max_cap=20_000_000_000,
            max_pages=5
        )
        if not coins:
            logging.info("No coins found with the specified market cap criteria, sir.")
            return []

        symbols = []
        for coin in coins:
            cmc_symbol = coin.get("symbol", "")
            if cmc_symbol:
                binance_symbol = cmc_symbol.upper() + "USDT"
                symbols.append(binance_symbol)

        valid_binance = get_valid_binance_symbols()
        filtered_symbols = [sym for sym in symbols if sym in valid_binance]

        save_filtered_symbols_to_file(filtered_symbols)
        logging.info(f"Filtered symbols: {filtered_symbols}")
        print("Save completed. Run the program again.")
        sys.exit()

    elif choice == "2":
        symbols = load_filtered_symbols_from_file()
        if symbols:
            logging.info(f"Loaded filtered symbols from file: {symbols}")
            return symbols
        else:
            logging.info("No symbols loaded from file.")
            return []
    else:
        logging.info("Invalid choice, sir. Exiting.")
        return []

###############################################################################
# FETCHING CANDLE DATA FROM BINANCE
###############################################################################
def fetch_candles(symbol: str, interval: str, limit=100, start_time: Optional[int] = None) -> pd.DataFrame:
    endpoint = f"{BASE_URL}/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": int(limit)
    }
    if start_time is not None:
        params["startTime"] = int(start_time)
        
    resp = retry_request(endpoint, method="GET", params=params, timeout=20, max_retries=5)
    if resp is None:
        logging.error(f"Failed to fetch {interval} klines for {symbol} after retries, sir.")
        return pd.DataFrame()
    try:
        raw = resp.json()
    except Exception as e:
        logging.error(f"JSON parse error for {symbol} {interval}: {e}")
        return pd.DataFrame()
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_asset_volume","num_trades",
        "taker_buy_base","taker_buy_quote","ignored"
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_values("open_time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df
