import logging
from typing import List, Dict, Optional, Tuple
from indicators import calculate_ema
from config import EMA_SHORT_PERIOD, EMA_LONG_PERIOD, TP_RATIO, SL_RATIO

logger = logging.getLogger(__name__)


class StockKwonStrategy:
    def __init__(self):
        self.ema_short = EMA_SHORT_PERIOD
        self.ema_long = EMA_LONG_PERIOD
        self.tp_ratio = TP_RATIO
        self.sl_ratio = SL_RATIO
    
    def analyze(self, candles: List[Dict], symbol: str = "") -> Optional[Dict]:
        if not candles or len(candles) < max(self.ema_short, self.ema_long):
            logger.debug(f"{symbol}: Insufficient data for analysis")
            return None
        
        close_prices = [c['close'] for c in candles]
        
        ema_short = calculate_ema(close_prices, self.ema_short)
        ema_long = calculate_ema(close_prices, self.ema_long)
        
        if not ema_short or not ema_long:
            logger.debug(f"{symbol}: Failed to calculate EMAs")
            return None
        
        recent_candles = candles[-10:]
        peak_info = self._find_single_peak(recent_candles)
        
        if not peak_info:
            logger.debug(f"{symbol}: No valid peak pattern found")
            return None
        
        peak_index, peak_price = peak_info
        
        if not self._check_bearish_after_peak(recent_candles, peak_index):
            logger.debug(f"{symbol}: No bearish pattern after peak")
            return None
        
        current_price = candles[-1]['close']
        current_low = candles[-1]['low']
        current_ema_short = ema_short[-1]
        current_ema_long = ema_long[-1]
        
        buy_condition_short = current_low < current_ema_short
        buy_condition_long = current_low < current_ema_long
        
        if not (buy_condition_short or buy_condition_long):
            logger.debug(f"{symbol}: Price not below EMA levels")
            return None
        
        entry_price = current_ema_short if buy_condition_short else current_ema_long
        ema_type = self.ema_short if buy_condition_short else self.ema_long
        
        volume_avg = sum(c['volume'] for c in candles[-20:]) / 20
        current_volume = candles[-1]['volume']
        volume_ratio = current_volume / volume_avg if volume_avg > 0 else 1
        
        signal_strength = self._calculate_signal_strength(
            candles, peak_price, current_price, volume_ratio
        )
        
        tp_price = entry_price * (1 + self.tp_ratio)
        sl_price = entry_price * (1 - self.sl_ratio)
        
        risk_reward = (tp_price - entry_price) / (entry_price - sl_price)
        
        return {
            'symbol': symbol,
            'signal': 'BUY',
            'entry_price': round(entry_price, 2),
            'current_price': round(current_price, 2),
            'tp_price': round(tp_price, 2),
            'sl_price': round(sl_price, 2),
            'peak_price': round(peak_price, 2),
            'ema_type': ema_type,
            'ema_short': round(current_ema_short, 2),
            'ema_long': round(current_ema_long, 2),
            'volume_ratio': round(volume_ratio, 2),
            'signal_strength': signal_strength,
            'risk_reward': round(risk_reward, 2),
            'peak_weeks_ago': len(recent_candles) - peak_index - 1,
            'price_from_peak': round((current_price - peak_price) / peak_price * 100, 2)
        }
    
    def _find_single_peak(self, candles: List[Dict]) -> Optional[Tuple[int, float]]:
        if len(candles) < 3:
            return None
        
        peaks = []
        for i in range(1, len(candles) - 1):
            if candles[i]['high'] > candles[i-1]['high'] and candles[i]['high'] > candles[i+1]['high']:
                peaks.append((i, candles[i]['high']))
        
        if len(peaks) != 1:
            return None
        
        peak_index, peak_price = peaks[0]
        
        if peak_index < 2 or peak_index > 7:
            return None
        
        all_highs = [c['high'] for c in candles]
        max_high = max(all_highs)
        if peak_price < max_high * 0.95:
            return None
        
        return peak_index, peak_price
    
    def _check_bearish_after_peak(self, candles: List[Dict], peak_index: int) -> bool:
        if peak_index >= len(candles) - 1:
            return False
        
        after_peak = candles[peak_index + 1:]
        
        if len(after_peak) < 2:
            return False
        
        bearish_count = 0
        for candle in after_peak:
            if candle['close'] < candle['open']:
                bearish_count += 1
            
            body = abs(candle['close'] - candle['open'])
            upper_wick = candle['high'] - max(candle['close'], candle['open'])
            
            if upper_wick > body * 1.5 and candle['close'] < candle['open']:
                bearish_count += 0.5
        
        return bearish_count >= len(after_peak) * 0.5
    
    def _calculate_signal_strength(self, candles: List[Dict], peak_price: float, 
                                  current_price: float, volume_ratio: float) -> str:
        strength_score = 0
        
        pullback_pct = abs((current_price - peak_price) / peak_price)
        if 0.15 <= pullback_pct <= 0.30:
            strength_score += 2
        elif 0.10 <= pullback_pct < 0.15:
            strength_score += 1
        
        if volume_ratio > 1.5:
            strength_score += 2
        elif volume_ratio > 1.0:
            strength_score += 1
        
        recent_volatility = self._calculate_volatility(candles[-20:])
        if recent_volatility < 0.03:
            strength_score += 1
        
        rsi = self._calculate_rsi(candles[-14:])
        if rsi and rsi < 40:
            strength_score += 2
        elif rsi and rsi < 50:
            strength_score += 1
        
        if strength_score >= 5:
            return "STRONG"
        elif strength_score >= 3:
            return "MODERATE"
        else:
            return "WEAK"
    
    def _calculate_volatility(self, candles: List[Dict]) -> float:
        if len(candles) < 2:
            return 0
        
        returns = []
        for i in range(1, len(candles)):
            ret = (candles[i]['close'] - candles[i-1]['close']) / candles[i-1]['close']
            returns.append(ret)
        
        if not returns:
            return 0
        
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        return variance ** 0.5
    
    def _calculate_rsi(self, candles: List[Dict], period: int = 14) -> Optional[float]:
        if len(candles) < period + 1:
            return None
        
        gains = []
        losses = []
        
        for i in range(1, len(candles)):
            change = candles[i]['close'] - candles[i-1]['close']
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def validate_signal(self, signal: Dict) -> bool:
        if signal['risk_reward'] < 1.5:
            logger.debug(f"{signal['symbol']}: Risk/reward ratio too low ({signal['risk_reward']})")
            return False
        
        if signal['signal_strength'] == "WEAK":
            logger.debug(f"{signal['symbol']}: Signal strength too weak")
            return False
        
        if signal['volume_ratio'] < 0.5:
            logger.debug(f"{signal['symbol']}: Volume too low")
            return False
        
        return True