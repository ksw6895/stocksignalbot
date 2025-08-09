import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from collections import deque

logger = logging.getLogger(__name__)


class FMPAPIClient:
    BASE_URL = "https://financialmodelingprep.com/api"
    
    def __init__(self, api_key: str, daily_limit: int = 250):
        self.api_key = api_key
        self.daily_limit = daily_limit
        self.request_count = 0
        self.request_timestamps = deque(maxlen=daily_limit)
        self.cache = {}
        self.cache_expiry = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'StockSignalBot/1.0'
        })
        
    def _check_rate_limit(self):
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        self.request_timestamps = deque(
            (ts for ts in self.request_timestamps if ts > day_ago),
            maxlen=self.daily_limit
        )
        
        if len(self.request_timestamps) >= self.daily_limit:
            oldest = self.request_timestamps[0]
            wait_time = (oldest + timedelta(days=1) - now).total_seconds()
            if wait_time > 0:
                logger.warning(f"Daily rate limit reached. Waiting {wait_time:.0f} seconds...")
                raise Exception(f"FMP API daily limit reached. Wait {wait_time:.0f} seconds.")
        
    def _make_request(self, endpoint: str, params: Optional[Dict] = None, cache_duration: int = 300) -> Any:
        cache_key = f"{endpoint}:{str(params)}"
        now = datetime.now()
        
        if cache_key in self.cache and cache_key in self.cache_expiry:
            if self.cache_expiry[cache_key] > now:
                logger.debug(f"Cache hit for {endpoint}")
                return self.cache[cache_key]
        
        self._check_rate_limit()
        
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            self.request_timestamps.append(now)
            self.request_count += 1
            
            data = response.json()
            
            self.cache[cache_key] = data
            self.cache_expiry[cache_key] = now + timedelta(seconds=cache_duration)
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"FMP API request failed: {e}")
            raise
    
    def get_nasdaq_stocks(self, min_market_cap: int = 500_000_000, 
                         max_market_cap: int = 50_000_000_000) -> List[Dict]:
        try:
            params = {
                'marketCapMoreThan': min_market_cap,
                'marketCapLowerThan': max_market_cap,
                'exchange': 'NASDAQ',
                'isActivelyTrading': 'true',
                'limit': 1000
            }
            
            data = self._make_request('/v3/stock-screener', params, cache_duration=3600)
            
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
            
            data = self._make_request(f'/v3/historical-price-full/{symbol}', params, cache_duration=3600)
            
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
            data = self._make_request(f'/v3/profile/{symbol}', cache_duration=7200)
            
            if data and len(data) > 0:
                return data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get company profile for {symbol}: {e}")
            return None
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        try:
            data = self._make_request(f'/v3/quote/{symbol}', cache_duration=60)
            
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
            data = self._make_request(endpoint, params, cache_duration=3600)
            
            return data if data else None
            
        except Exception as e:
            logger.error(f"Failed to get {indicator} for {symbol}: {e}")
            return None
    
    def is_market_open(self) -> bool:
        try:
            data = self._make_request('/v3/is-the-market-open', cache_duration=60)
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
            data = self._make_request('/v3/market-hours', cache_duration=3600)
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
        self.cache.clear()
        self.cache_expiry.clear()
        logger.info("FMP API cache cleared")
    
    def get_remaining_requests(self) -> int:
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        recent_requests = sum(1 for ts in self.request_timestamps if ts > day_ago)
        return max(0, self.daily_limit - recent_requests)