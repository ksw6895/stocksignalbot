import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import time
from fmp_api import FMPAPIClient
from config import (
    FMP_API_KEY, MIN_MARKET_CAP, MAX_MARKET_CAP,
    MIN_VOLUME, MIN_PRICE, MAX_PRICE, BATCH_SIZE,
    WATCHLIST_SYMBOLS, EXCLUDED_SYMBOLS, FMP_DAILY_LIMIT
)

logger = logging.getLogger(__name__)


class StockDataFetcher:
    def __init__(self):
        self.fmp_client = FMPAPIClient(FMP_API_KEY, daily_limit=FMP_DAILY_LIMIT)
        self.last_scan_time = None
        self.cached_stocks = []
        self.cache_duration = timedelta(hours=1)
    
    def get_filtered_stocks(self, force_refresh: bool = False) -> List[Dict]:
        now = datetime.now()
        
        if not force_refresh and self.cached_stocks and self.last_scan_time:
            if now - self.last_scan_time < self.cache_duration:
                logger.info(f"Using cached stock list ({len(self.cached_stocks)} stocks)")
                return self.cached_stocks
        
        logger.info(f"Fetching NASDAQ stocks (Market Cap: ${MIN_MARKET_CAP:,} - ${MAX_MARKET_CAP:,})")
        
        try:
            if WATCHLIST_SYMBOLS:
                stocks = []
                for symbol in WATCHLIST_SYMBOLS:
                    if symbol not in EXCLUDED_SYMBOLS:
                        profile = self.fmp_client.get_company_profile(symbol)
                        if profile and self._validate_stock(profile):
                            stocks.append({
                                'symbol': symbol,
                                'companyName': profile.get('companyName', symbol),
                                'marketCap': profile.get('mktCap', 0),
                                'price': profile.get('price', 0),
                                'volume': profile.get('volAvg', 0),
                                'sector': profile.get('sector', 'Unknown'),
                                'industry': profile.get('industry', 'Unknown')
                            })
                logger.info(f"Loaded {len(stocks)} stocks from watchlist")
            else:
                all_stocks = self.fmp_client.get_nasdaq_stocks(MIN_MARKET_CAP, MAX_MARKET_CAP)
                
                stocks = []
                for stock in all_stocks:
                    if stock.get('symbol') not in EXCLUDED_SYMBOLS and self._validate_stock(stock):
                        stocks.append({
                            'symbol': stock.get('symbol'),
                            'companyName': stock.get('companyName', stock.get('symbol')),
                            'marketCap': stock.get('marketCap', 0),
                            'price': stock.get('price', 0),
                            'volume': stock.get('volume', 0),
                            'sector': stock.get('sector', 'Unknown'),
                            'industry': stock.get('industry', 'Unknown')
                        })
                
                logger.info(f"Found {len(stocks)} NASDAQ stocks matching criteria")
            
            self.cached_stocks = stocks
            self.last_scan_time = now
            
            return stocks
            
        except Exception as e:
            logger.error(f"Error fetching stocks: {e}")
            return self.cached_stocks if self.cached_stocks else []
    
    def _validate_stock(self, stock: Dict) -> bool:
        price = stock.get('price', 0)
        volume = stock.get('volume', 0) or stock.get('volAvg', 0)
        market_cap = stock.get('marketCap', 0) or stock.get('mktCap', 0)
        
        if price < MIN_PRICE or price > MAX_PRICE:
            return False
        
        if volume < MIN_VOLUME:
            return False
        
        if market_cap < MIN_MARKET_CAP or market_cap > MAX_MARKET_CAP:
            return False
        
        return True
    
    def fetch_weekly_candles(self, symbol: str, limit: int = 52) -> Optional[List[Dict]]:
        try:
            logger.debug(f"Fetching weekly candles for {symbol}")
            
            candles = self.fmp_client.get_historical_weekly(symbol, limit)
            
            if not candles:
                logger.warning(f"No candle data available for {symbol}")
                return None
            
            formatted_candles = []
            for candle in candles:
                formatted_candles.append({
                    'timestamp': self._date_to_timestamp(candle['date']),
                    'open': float(candle['open']),
                    'high': float(candle['high']),
                    'low': float(candle['low']),
                    'close': float(candle['close']),
                    'volume': float(candle.get('volume', 0))
                })
            
            return formatted_candles
            
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
            return None
    
    def _date_to_timestamp(self, date_str: str) -> int:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return int(dt.timestamp() * 1000)
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            quote = self.fmp_client.get_quote(symbol)
            if quote:
                return float(quote.get('price', 0))
            return None
        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            return None
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        try:
            profile = self.fmp_client.get_company_profile(symbol)
            quote = self.fmp_client.get_quote(symbol)
            
            if not profile or not quote:
                return None
            
            return {
                'symbol': symbol,
                'name': profile.get('companyName', symbol),
                'price': float(quote.get('price', 0)),
                'marketCap': profile.get('mktCap', 0),
                'volume': quote.get('volume', 0),
                'avgVolume': quote.get('avgVolume', 0),
                'dayHigh': quote.get('dayHigh', 0),
                'dayLow': quote.get('dayLow', 0),
                'yearHigh': quote.get('yearHigh', 0),
                'yearLow': quote.get('yearLow', 0),
                'pe': quote.get('pe', 0),
                'eps': quote.get('eps', 0),
                'sector': profile.get('sector', 'Unknown'),
                'industry': profile.get('industry', 'Unknown'),
                'description': profile.get('description', '')[:200]
            }
            
        except Exception as e:
            logger.error(f"Error fetching stock info for {symbol}: {e}")
            return None
    
    def is_market_open(self) -> bool:
        return self.fmp_client.is_market_open()
    
    def get_market_hours(self) -> Dict:
        return self.fmp_client.get_market_hours()
    
    def process_stocks_in_batches(self, stocks: List[Dict], processor_func, batch_size: int = None) -> List:
        if batch_size is None:
            batch_size = BATCH_SIZE
        
        results = []
        total = len(stocks)
        
        for i in range(0, total, batch_size):
            batch = stocks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total + batch_size - 1) // batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} stocks)")
            
            for stock in batch:
                try:
                    result = processor_func(stock)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {stock.get('symbol', 'unknown')}: {e}")
            
            remaining_requests = self.fmp_client.get_remaining_requests()
            if remaining_requests < 10:
                logger.warning(f"Low API quota: {remaining_requests} requests remaining")
                if i + batch_size < total:
                    logger.info("Pausing to preserve API quota...")
                    time.sleep(60)
        
        return results
    
    def clear_cache(self):
        self.fmp_client.clear_cache()
        self.cached_stocks = []
        self.last_scan_time = None
        logger.info("Stock data cache cleared")