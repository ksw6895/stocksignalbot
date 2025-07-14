import pandas as pd

def compute_ema_series(prices: pd.Series, period: int) -> pd.Series:
    """
    Compute EMA with period. If not enough data => 
    fill the earliest row with None until we can start the EMA.
    """
    if len(prices) < period:
        return pd.Series([None]*len(prices), index=prices.index)
    alpha = 2.0 / (period + 1)
    ema_values = [None]*(period-1)
    initial_sma = prices.iloc[:period].mean()
    ema_values.append(initial_sma)
    for i in range(period, len(prices)):
        prev_ema = ema_values[-1]
        curr_val = prices.iloc[i]
        curr_ema = curr_val * alpha + prev_ema * (1 - alpha)
        ema_values.append(curr_ema)
    return pd.Series(ema_values, index=prices.index)
