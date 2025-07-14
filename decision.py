import pandas as pd
from typing import Optional
from indicators import compute_ema_series

###############################################################################
# UPPER SECTION STRATEGY LOGIC
###############################################################################
def check_single_peak(highs: pd.Series, closes: pd.Series, recent_window=7, total_window=200) -> int:
    """
    Single-peak condition:
    1. Highest candle within total_window is in the recent_window
    2. The high price at peak should be at least 20% bigger than 15-EMA
    3. At least one recent close is higher than older highs
    4. The peak candle's close or its previous candle's close 
       is above all prior highs
    """
    if len(highs) < recent_window + 7 or len(closes) < recent_window + 7:
        return -1

    if total_window < recent_window + 7:
        return -1

    mod_window = min(len(highs), total_window)
    subset_highs = highs.iloc[-mod_window:]
    max_val = subset_highs.max()
    max_indices = subset_highs[subset_highs == max_val].index
    if len(max_indices) != 1:
        return -1
    peak_idx = max_indices[0]

    # check if that peak is in the last `recent_window` of the subset
    if peak_idx not in subset_highs.iloc[-recent_window:].index:
        return -1

    subset_closes = closes.iloc[-mod_window:]
    ema_series = compute_ema_series(subset_closes, 15)
    
    # Check if EMA value is None before comparison
    ema_value = ema_series[peak_idx]
    if ema_value is None or pd.isna(ema_value):
        return -1
    
    if subset_highs[peak_idx] < 1.2 * ema_value:
        return -1

    split_point = mod_window - recent_window - 1
    if split_point < 0:
        return -1
    earlier_highs = subset_highs.iloc[:split_point]
    max_earlier_high = earlier_highs.max() if not earlier_highs.empty else float('-inf')
    recent_closes = subset_closes.iloc[-(recent_window + 1):]
    if not (recent_closes > max_earlier_high).any():
        return -1

    peak_loc = subset_highs.index.get_loc(peak_idx)
    if peak_loc > 0:
        peak_close = subset_closes.iloc[peak_loc]
        prev_close = subset_closes.iloc[peak_loc - 1]
        prev_highs = subset_highs.iloc[:peak_loc - 1]
        max_prev_high = prev_highs.max() if not prev_highs.empty else float('-inf')
        if peak_close <= max_prev_high and prev_close <= max_prev_high:
            return -1
    
    return peak_idx

def check_bearish_pattern(df: pd.DataFrame, window=7, start_idx: Optional[int] = None, buffer=0.1) -> str:
    """
    We look at up to 'window' candles after the peak. 
    'all' => all are 'bearish'
    'all_but_one' => exactly 1 bullish, rest bearish
    'none' => anything else
    """
    pos = None
    if start_idx is not None:
        try:
            pos = df.index.get_loc(start_idx)
            sub = df.iloc[pos : pos + window]
        except KeyError:
            sub = df.tail(window)
    else:
        sub = df.tail(window)

    if len(sub) == 0:
        return "none"

    statuses = []
    for i in range(len(sub)):
        if i == 0:
            if pos is not None and pos > 0:
                prev_candle = df.iloc[pos - 1]
                this_candle = sub.iloc[i]
                if this_candle["high"] > prev_candle["high"]:
                    statuses.append("bullish")
                elif this_candle["close"] > this_candle["open"]:
                    statuses.append("bullish")
                elif this_candle["high"] > (1 + buffer) * this_candle["open"]:
                    statuses.append("bullish")
                else:
                    statuses.append("bearish")
            else:
                statuses.append("bearish")
        else:
            curr = sub.iloc[i]
            prev = sub.iloc[i - 1]
            if curr["high"] > prev["high"]:
                statuses.append("bullish")
            elif curr["close"] > curr["open"]:
                statuses.append("bullish")
            elif curr["high"] > (1 + buffer) * curr["open"]:
                statuses.append("bullish")
            else:
                statuses.append("bearish")

    n_bearish = sum(s == "bearish" for s in statuses)
    total_count = len(statuses)
    if n_bearish == total_count:
        return "all"
    elif n_bearish == (total_count - 1):
        return "all_but_one"
    else:
        return "none"

def is_low_under_ema(df: pd.DataFrame, period: int) -> bool:
    if len(df) < 2:
        return False
    ema_series = compute_ema_series(df["close"], period)
    last_idx = len(df) - 1
    curr_low = df["low"].iloc[last_idx]
    curr_ema = ema_series.iloc[last_idx]
    return curr_low < curr_ema

def check_upper_section(df: pd.DataFrame, interval: str) -> str:
    """
    UPPER SECTION STRATEGY LOGIC
    1) Identify single peak
    2) Check pattern => 'all' or 'all_but_one' 
    3) If yes => use EMA(15) or EMA(33)
    """
    if interval == "1w":
        recent_window = 5
        total_window = 52
    elif interval == "1d":
        recent_window = 7
        total_window = 200
    else:
        recent_window = 7
        total_window = 200
        
    peak_idx = check_single_peak(df["high"], df["close"], recent_window=recent_window, total_window=total_window)
    if peak_idx == -1:
        return "NO"

    if interval == "1w":
        pattern = check_bearish_pattern(df, start_idx=peak_idx + 1, buffer=0.2)
    elif interval == "1d":
        pattern = check_bearish_pattern(df, start_idx=peak_idx + 1, buffer=0.1)
    else:
        pattern = check_bearish_pattern(df, start_idx=peak_idx + 1, buffer=0.1)

    if pattern not in ("all", "all_but_one"):
        return "NO"

    use_period = 15 if pattern == "all" else 33
    if is_low_under_ema(df, use_period):
        return f"INITIAL_YES_{use_period}"
    return "NO"

def generate_trade_signal(df: pd.DataFrame, initial_signal: str,
                          tp_ratio: float = 0.1, sl_ratio: float = 0.05) -> dict:
    if not initial_signal.startswith("INITIAL_YES"):
        return {'signal': 'NO', 'entry_price': None, 'tp_price': None, 'sl_price': None, 'ema_period': None}
    
    ema_period = int(initial_signal.split('_')[-1])
    ema_series = compute_ema_series(df["close"], ema_period)
    
    # Get weekly EMA as initial entry price
    weekly_ema = ema_series.iloc[-1]
    
    # For backtesting, actual entry will be determined in TWAP function
    # using min(first_hour_open, weekly_ema)
    entry_price = weekly_ema
    
    # Calculate initial TP/SL based on weekly EMA
    # These will be recalculated in TWAP based on real entry price
    tp_price = entry_price * (1 + tp_ratio)
    sl_price = entry_price * (1 - sl_ratio)

    return {
        'signal': 'BUY',
        'entry_price': entry_price,  # This is weekly EMA
        'tp_price': tp_price,
        'sl_price': sl_price,
        'ema_period': ema_period
    }

def kwon_strategy_decision(df: pd.DataFrame, interval: str,
                           tp_ratio: float = 0.1, sl_ratio: float = 0.05) -> dict:
    """
    1. Get initial signal
    2. Generate trade signal with TP/SL if initial signal is positive
    """
    initial_signal = check_upper_section(df, interval)
    final = generate_trade_signal(df, initial_signal, tp_ratio, sl_ratio)
    if final['signal'] == 'BUY':
        final['decision'] = f"YES_{final['ema_period']}"
    else:
        final['decision'] = 'NO'
    return final
