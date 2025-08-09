import logging
import pandas as pd
from typing import List, Dict, Optional, Tuple
from indicators import compute_ema_series
from config import TP_RATIO, SL_RATIO

logger = logging.getLogger(__name__)


class UpperSectionStrategy:
    """
    Upper Section Strategy implementation
    Identifies single peak patterns followed by bearish candles
    """
    
    def __init__(self):
        self.tp_ratio = TP_RATIO if TP_RATIO else 0.10  # Default 10%
        self.sl_ratio = SL_RATIO if SL_RATIO else 0.05  # Default 5%
    
    def analyze(self, candles: List[Dict], symbol: str = "", interval: str = "1d") -> Optional[Dict]:
        """
        Main analysis function for Upper Section Strategy
        
        Args:
            candles: List of OHLC candle data
            symbol: Stock symbol
            interval: Timeframe ('1d' for daily, '1w' for weekly)
        
        Returns:
            Signal dictionary if conditions met, None otherwise
        """
        if not candles or len(candles) < 35:
            logger.debug(f"{symbol}: Insufficient data for analysis (need 35+, got {len(candles)})")
            return None
        
        # Convert to DataFrame for easier processing
        df = pd.DataFrame(candles)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        df = df.sort_index()
        
        # Determine parameters based on interval
        if interval == "1w":
            recent_window = 5
            total_window = 52
            buffer = 0.2
        else:  # Default to daily
            recent_window = 7
            total_window = 200
            buffer = 0.1
        
        # Step 1: Check for single peak
        peak_idx = self._check_single_peak(df, recent_window, total_window)
        if peak_idx == -1:
            logger.debug(f"{symbol}: No valid single peak found")
            return None
        
        logger.info(f"{symbol}: Found single peak at index {peak_idx}")
        
        # Step 2: Check bearish pattern after peak
        pattern = self._check_bearish_pattern(df, window=7, start_idx=peak_idx, buffer=buffer)
        if pattern == "none":
            logger.debug(f"{symbol}: No valid bearish pattern after peak")
            return None
        
        logger.info(f"{symbol}: Bearish pattern detected: {pattern}")
        
        # Step 3: Determine EMA period based on pattern
        if pattern == "all":
            ema_period = 15
        elif pattern == "all_but_one":
            ema_period = 33
        else:
            logger.debug(f"{symbol}: Invalid pattern type: {pattern}")
            return None
        
        # Step 4: Check if low is under EMA
        if not self._is_low_under_ema(df, ema_period):
            logger.debug(f"{symbol}: Current low not below EMA{ema_period}")
            return None
        
        logger.info(f"{symbol}: Low is below EMA{ema_period}, generating signal")
        
        # Step 5: Generate trade signal
        signal = self._generate_trade_signal(df, symbol, ema_period)
        
        if signal:
            signal['pattern'] = pattern
            signal['peak_index'] = peak_idx
            signal['interval'] = interval
        
        return signal
    
    def _check_single_peak(self, df: pd.DataFrame, recent_window: int, total_window: int) -> int:
        """
        Check for single peak pattern according to strategy documentation
        
        Returns:
            Index of the peak if found, -1 otherwise
        """
        highs = df['high']
        closes = df['close']
        
        # Get the window of data to analyze
        mod_window = min(len(df), total_window)
        subset_df = df.iloc[-mod_window:]
        subset_highs = subset_df['high']
        subset_closes = subset_df['close']
        
        # Find the maximum high in the window
        max_val = subset_highs.max()
        max_indices = subset_highs[subset_highs == max_val].index
        
        # Must be a single peak
        if len(max_indices) != 1:
            logger.debug(f"Multiple peaks found: {len(max_indices)}")
            return -1
        
        peak_idx = max_indices[0]
        
        # Peak must be in recent window
        if peak_idx not in subset_df.iloc[-recent_window:].index:
            logger.debug(f"Peak not in recent window")
            return -1
        
        # Check EMA condition (peak must be 1.2x EMA15)
        ema_series = compute_ema_series(subset_closes, 15)
        if peak_idx not in ema_series.index or pd.isna(ema_series[peak_idx]):
            logger.debug(f"Cannot compute EMA at peak")
            return -1
        
        ema_value = ema_series[peak_idx]
        if subset_highs[peak_idx] < 1.2 * ema_value:
            logger.debug(f"Peak not 20% above EMA15: {subset_highs[peak_idx]} < {1.2 * ema_value}")
            return -1
        
        # Check breakout condition
        split_point = mod_window - recent_window - 1
        if split_point > 0:
            earlier_highs = subset_highs.iloc[:split_point]
            if len(earlier_highs) > 0:
                max_earlier_high = earlier_highs.max()
                recent_closes = subset_closes.iloc[-(recent_window + 1):]
                if not (recent_closes > max_earlier_high).any():
                    logger.debug(f"No breakout detected")
                    return -1
        
        # Check peak candle close condition
        peak_loc = subset_df.index.get_loc(peak_idx)
        if peak_loc > 0:
            peak_close = subset_closes.iloc[peak_loc]
            prev_close = subset_closes.iloc[peak_loc - 1]
            prev_highs = subset_highs.iloc[:peak_loc - 1]
            if len(prev_highs) > 0:
                max_prev_high = prev_highs.max()
                if peak_close <= max_prev_high and prev_close <= max_prev_high:
                    logger.debug(f"Peak candle close condition not met")
                    return -1
        
        return peak_idx
    
    def _check_bearish_pattern(self, df: pd.DataFrame, window: int = 7, 
                               start_idx: Optional[pd.Timestamp] = None, buffer: float = 0.1) -> str:
        """
        Check bearish pattern after peak according to strategy documentation
        
        Returns:
            "all" - All candles are bearish (use EMA15)
            "all_but_one" - All but one candle are bearish (use EMA33)
            "none" - Pattern not valid
        """
        # Get candles after the peak
        pos = None
        if start_idx is not None:
            try:
                pos = df.index.get_loc(start_idx)
                # Start from the candle AFTER the peak
                sub = df.iloc[pos + 1 : pos + 1 + window]
            except (KeyError, IndexError):
                sub = df.tail(window)
        else:
            sub = df.tail(window)
        
        if len(sub) == 0:
            return "none"
        
        # Classify each candle as bullish or bearish
        statuses = []
        
        for i in range(len(sub)):
            if i == 0:
                # First candle after peak
                if pos is not None and pos >= 0:
                    prev_candle = df.iloc[pos]  # Peak candle
                    this_candle = sub.iloc[i]   # First candle after peak
                    
                    # Three conditions for bullish (OR logic)
                    if this_candle["high"] > prev_candle["high"]:
                        statuses.append("bullish")
                    elif this_candle["close"] > this_candle["open"]:
                        statuses.append("bullish")
                    elif this_candle["high"] > (1 + buffer) * this_candle["open"]:
                        statuses.append("bullish")
                    else:
                        statuses.append("bearish")
                else:
                    # If we can't get previous candle, default to bearish
                    statuses.append("bearish")
            else:
                # Subsequent candles
                curr = sub.iloc[i]
                prev = sub.iloc[i - 1]
                
                # Same three conditions
                if curr["high"] > prev["high"]:
                    statuses.append("bullish")
                elif curr["close"] > curr["open"]:
                    statuses.append("bullish")
                elif curr["high"] > (1 + buffer) * curr["open"]:
                    statuses.append("bullish")
                else:
                    statuses.append("bearish")
        
        # Count bearish candles
        n_bearish = sum(s == "bearish" for s in statuses)
        total_count = len(statuses)
        
        logger.debug(f"Bearish pattern: {n_bearish}/{total_count} bearish candles")
        
        # Determine pattern type
        if n_bearish == total_count:
            return "all"  # All bearish -> EMA15
        elif n_bearish == (total_count - 1):
            return "all_but_one"  # All but one bearish -> EMA33
        else:
            return "none"  # Too many bullish candles
    
    def _is_low_under_ema(self, df: pd.DataFrame, period: int) -> bool:
        """
        Check if current candle's low is below EMA
        
        Args:
            df: Candle data
            period: EMA period (15 or 33)
        
        Returns:
            True if low < EMA, False otherwise
        """
        ema_series = compute_ema_series(df["close"], period)
        last_idx = len(df) - 1
        curr_low = df["low"].iloc[last_idx]
        curr_ema = ema_series.iloc[last_idx]
        
        if pd.isna(curr_ema):
            return False
        
        return curr_low < curr_ema
    
    def _generate_trade_signal(self, df: pd.DataFrame, symbol: str, ema_period: int) -> Optional[Dict]:
        """
        Generate trading signal with entry, TP, and SL prices
        
        Args:
            df: Candle data
            symbol: Stock symbol
            ema_period: EMA period to use (15 or 33)
        
        Returns:
            Signal dictionary with trade parameters
        """
        # Calculate EMA value for entry
        ema_series = compute_ema_series(df["close"], ema_period)
        last_idx = len(df) - 1
        entry_price = ema_series.iloc[last_idx]
        
        if pd.isna(entry_price):
            return None
        
        # Get current price info
        current_price = df["close"].iloc[last_idx]
        current_low = df["low"].iloc[last_idx]
        current_high = df["high"].iloc[last_idx]
        
        # Calculate TP and SL
        tp_price = entry_price * (1 + self.tp_ratio)
        sl_price = entry_price * (1 - self.sl_ratio)
        
        # Calculate risk/reward ratio
        risk = entry_price - sl_price
        reward = tp_price - entry_price
        risk_reward = reward / risk if risk > 0 else 0
        
        # Get additional metrics
        volume = df["volume"].iloc[last_idx] if "volume" in df.columns else 0
        
        # Calculate price change from peak
        peak_high = df["high"].max()
        price_from_peak = ((current_price - peak_high) / peak_high * 100) if peak_high > 0 else 0
        
        return {
            'symbol': symbol,
            'signal': 'BUY',
            'decision': f'YES_{ema_period}',
            'entry_price': round(float(entry_price), 2),
            'current_price': round(float(current_price), 2),
            'current_low': round(float(current_low), 2),
            'current_high': round(float(current_high), 2),
            'tp_price': round(float(tp_price), 2),
            'sl_price': round(float(sl_price), 2),
            'tp_ratio': self.tp_ratio,
            'sl_ratio': self.sl_ratio,
            'ema_period': ema_period,
            'risk_reward': round(risk_reward, 2),
            'volume': int(volume),
            'price_from_peak': round(price_from_peak, 2),
            'peak_high': round(float(peak_high), 2)
        }
    
    def validate_signal(self, signal: Dict) -> bool:
        """
        Validate signal quality
        
        Args:
            signal: Signal dictionary
        
        Returns:
            True if signal is valid, False otherwise
        """
        # Basic validation
        if signal.get('risk_reward', 0) < 1.5:
            logger.debug(f"{signal['symbol']}: Risk/reward ratio too low ({signal.get('risk_reward', 0)})")
            return False
        
        # Ensure entry price is reasonable
        if signal['entry_price'] <= 0:
            logger.debug(f"{signal['symbol']}: Invalid entry price")
            return False
        
        # Check if current price is not too far from entry
        price_diff = abs(signal['current_price'] - signal['entry_price']) / signal['entry_price']
        if price_diff > 0.1:  # More than 10% difference
            logger.debug(f"{signal['symbol']}: Price too far from entry ({price_diff:.2%})")
            return False
        
        return True


# Backward compatibility
StockKwonStrategy = UpperSectionStrategy