import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class FMPAPIClient:
    BASE_URL = "https://financialmodelingprep.com/api"
    
    def __init__(self, api_key: str, daily_limit: int = 250):
        self.api_key = api_key
        self.daily_limit = daily_limit
        self.request_count = 0
        self.request_timestamps = deque(maxlen=1000)  # Track request timestamps with limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'StockSignalBot/1.0'
        })
        
        # Exponential backoff settings
        self.max_retries = 6  # 1s, 2s, 4s, 8s, 16s, 32s
        self.base_delay = 1.0  # Start with 1 second
        
    def _make_request(self, endpoint: str, params: Optional[Dict] = None, cache_duration: int = 300) -> Any:
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{self.BASE_URL}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                self.request_count += 1
                self.request_timestamps.append(datetime.now())  # Track request timestamp
                
                if response.status_code == 200:
                    data = response.json()
                    return data
                elif response.status_code == 429:
                    # Rate limit hit - exponential backoff
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Rate limit hit (429), retrying in {delay} seconds (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(delay)
                    continue
                elif response.status_code in [500, 502, 503, 504]:
                    # Server error - exponential backoff
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Server error {response.status_code}, retrying in {delay} seconds")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    raise requests.exceptions.RequestException(f"Status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                delay = self.base_delay * (2 ** attempt)
                logger.warning(f"Request timeout, retrying in {delay} seconds")
                time.sleep(delay)
                continue
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Request error: {e}, retrying in {delay} seconds")
                    time.sleep(delay)
                    continue
                logger.error(f"FMP API request failed after {self.max_retries} attempts: {e}")
                raise
        
        logger.error(f"Max retries ({self.max_retries}) reached for {endpoint}")
        raise Exception(f"Failed to complete request after {self.max_retries} attempts")
    
    def get_nasdaq_stocks(self, min_market_cap: int = 500_000_000, 
                         max_market_cap: int = 50_000_000_000) -> List[Dict]:
        try:
            params = {
                'marketCapMoreThan': min_market_cap,
                'marketCapLowerThan': max_market_cap,
                'exchange': 'NASDAQ',
                'isActivelyTrading': 'true',
                'limit': 10000  # Set high enough to get all NASDAQ stocks (max ~8000)
            }
            
            data = self._make_request('/v3/stock-screener', params)
            
            if not data:
                return []
            
            filtered = [
                stock for stock in data
                if stock.get('marketCap', 0) >= min_market_cap
                and stock.get('marketCap', 0) <= max_market_cap
                and stock.get('volume', 0) > 100000
            ]
            
            return filtered
            
        except Exception as e:
            logger.error(f"Failed to get NASDAQ stocks: {e}")
            return []
    
    def get_historical_weekly(self, symbol: str, limit: int = 52) -> List[Dict]:
        try:
            now = datetime.now()
            from_date = (now - timedelta(weeks=limit)).strftime('%Y-%m-%d')
            to_date = now.strftime('%Y-%m-%d')
            
            params = {
                'from': from_date,
                'to': to_date
            }
            
            data = self._make_request(f'/v3/historical-price-full/{symbol}', params)
            
            if not data or 'historical' not in data:
                return []
            
            daily_data = data['historical']
            
            weekly_data = self._convert_to_weekly(daily_data)
            
            return weekly_data[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            return []
    
    def _convert_to_weekly(self, daily_data: List[Dict]) -> List[Dict]:
        if not daily_data:
            return []
        
        weekly_candles = []
        current_week = []
        
        for day in sorted(daily_data, key=lambda x: x['date']):
            date = datetime.strptime(day['date'], '%Y-%m-%d')
            
            if not current_week:
                current_week = [day]
            elif date.weekday() < datetime.strptime(current_week[-1]['date'], '%Y-%m-%d').weekday():
                weekly_candle = {
                    'date': current_week[0]['date'],
                    'open': current_week[0]['open'],
                    'high': max(d['high'] for d in current_week),
                    'low': min(d['low'] for d in current_week),
                    'close': current_week[-1]['close'],
                    'volume': sum(d.get('volume', 0) for d in current_week)
                }
                weekly_candles.append(weekly_candle)
                current_week = [day]
            else:
                current_week.append(day)
        
        if current_week:
            weekly_candle = {
                'date': current_week[0]['date'],
                'open': current_week[0]['open'],
                'high': max(d['high'] for d in current_week),
                'low': min(d['low'] for d in current_week),
                'close': current_week[-1]['close'],
                'volume': sum(d.get('volume', 0) for d in current_week)
            }
            weekly_candles.append(weekly_candle)
        
        return list(reversed(weekly_candles))
    
    def get_company_profile(self, symbol: str) -> Optional[Dict]:
        try:
            data = self._make_request(f'/v3/profile/{symbol}')
            
            if data and len(data) > 0:
                return data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get company profile for {symbol}: {e}")
            return None
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        try:
            data = self._make_request(f'/v3/quote/{symbol}')
            
            if data and len(data) > 0:
                return data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return None
    
    def get_technical_indicator(self, symbol: str, indicator: str = 'ema', 
                               period: int = 20, interval: str = 'weekly') -> Optional[List[Dict]]:
        try:
            params = {
                'period': period,
                'type': indicator
            }
            
            endpoint = f'/v3/technical_indicator/{interval}/{indicator.upper()}/{symbol}'
            data = self._make_request(endpoint, params)
            
            return data if data else None
            
        except Exception as e:
            logger.error(f"Failed to get {indicator} for {symbol}: {e}")
            return None
    
    def is_market_open(self) -> bool:
        try:
            data = self._make_request('/v3/is-the-market-open')
            return data.get('isTheMarketOpen', False)
        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            
            now = datetime.now()
            if now.weekday() >= 5:
                return False
            
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            
            return market_open <= now <= market_close
    
    def get_market_hours(self) -> Dict:
        try:
            data = self._make_request('/v3/market-hours')
            return data if data else {
                'isTheMarketOpen': False,
                'marketOpen': '09:30:00',
                'marketClose': '16:00:00'
            }
        except Exception as e:
            logger.error(f"Failed to get market hours: {e}")
            return {
                'isTheMarketOpen': False,
                'marketOpen': '09:30:00',
                'marketClose': '16:00:00'
            }
    
    def clear_cache(self):
        # No cache to clear anymore
        logger.info("Cache functionality removed")
    
    def get_remaining_requests(self) -> int:
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        # Clean up old timestamps
        while self.request_timestamps and self.request_timestamps[0] <= day_ago:
            self.request_timestamps.popleft()
        
        recent_requests = len(self.request_timestamps)
        return max(0, self.daily_limit - recent_requests)