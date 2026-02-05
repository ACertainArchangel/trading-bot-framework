"""
Technical indicators for strategy development.

All indicators operate on lists of Candles and return computed values.
These are pure functions with no side effects.
"""

from typing import List, Optional
from ..core.candle import Candle
import math


def ema(candles: List[Candle], period: int, use_close: bool = True) -> List[float]:
    """
    Calculate Exponential Moving Average.
    
    Args:
        candles: List of Candle objects
        period: EMA period (e.g., 12, 26, 50)
        use_close: If True, use close price; else use typical price
    
    Returns:
        List of EMA values (same length as candles, None for insufficient data)
    
    Example:
        >>> ema_12 = ema(candles, 12)
        >>> current_ema = ema_12[-1]
    """
    if len(candles) < period:
        return [None] * len(candles)
    
    prices = [c.close if use_close else (c.high + c.low + c.close) / 3 for c in candles]
    multiplier = 2 / (period + 1)
    
    result = [None] * (period - 1)
    
    # First EMA is SMA
    first_ema = sum(prices[:period]) / period
    result.append(first_ema)
    
    # Calculate subsequent EMAs
    for i in range(period, len(prices)):
        new_ema = (prices[i] - result[-1]) * multiplier + result[-1]
        result.append(new_ema)
    
    return result


def sma(candles: List[Candle], period: int) -> List[float]:
    """
    Calculate Simple Moving Average.
    
    Args:
        candles: List of Candle objects
        period: SMA period (e.g., 20, 50, 200)
    
    Returns:
        List of SMA values (None for insufficient data points)
    """
    if len(candles) < period:
        return [None] * len(candles)
    
    prices = [c.close for c in candles]
    result = [None] * (period - 1)
    
    for i in range(period - 1, len(prices)):
        avg = sum(prices[i - period + 1:i + 1]) / period
        result.append(avg)
    
    return result


def rsi(candles: List[Candle], period: int = 14) -> List[float]:
    """
    Calculate Relative Strength Index.
    
    Args:
        candles: List of Candle objects
        period: RSI period (default: 14)
    
    Returns:
        List of RSI values (0-100 range, None for insufficient data)
    
    Example:
        >>> rsi_values = rsi(candles, 14)
        >>> if rsi_values[-1] < 30:
        ...     print("Oversold!")
    """
    if len(candles) < period + 1:
        return [None] * len(candles)
    
    prices = [c.close for c in candles]
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    
    result = [None] * period
    
    # First RSI uses simple average
    gains = [d if d > 0 else 0 for d in deltas[:period]]
    losses = [-d if d < 0 else 0 for d in deltas[:period]]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - (100 / (1 + rs)))
    
    # Subsequent RSIs use smoothed average
    for i in range(period, len(deltas)):
        delta = deltas[i]
        gain = delta if delta > 0 else 0
        loss = -delta if delta < 0 else 0
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))
    
    return result


def macd(candles: List[Candle], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        candles: List of Candle objects
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal line period (default: 9)
    
    Returns:
        Dict with 'macd', 'signal', 'histogram' lists
    
    Example:
        >>> m = macd(candles)
        >>> if m['macd'][-1] > m['signal'][-1]:
        ...     print("Bullish crossover!")
    """
    fast_ema = ema(candles, fast)
    slow_ema = ema(candles, slow)
    
    # MACD line = fast EMA - slow EMA
    macd_line = []
    for i in range(len(candles)):
        if fast_ema[i] is None or slow_ema[i] is None:
            macd_line.append(None)
        else:
            macd_line.append(fast_ema[i] - slow_ema[i])
    
    # Signal line = EMA of MACD line
    # Create "fake" candles with MACD values as close prices for EMA calculation
    valid_macd = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    
    signal_line = [None] * len(candles)
    if len(valid_macd) >= signal:
        macd_values = [v for _, v in valid_macd]
        multiplier = 2 / (signal + 1)
        
        # First signal is SMA
        first_signal = sum(macd_values[:signal]) / signal
        signal_idx = valid_macd[signal - 1][0]
        signal_line[signal_idx] = first_signal
        
        prev_signal = first_signal
        for j in range(signal, len(valid_macd)):
            idx = valid_macd[j][0]
            new_signal = (macd_values[j] - prev_signal) * multiplier + prev_signal
            signal_line[idx] = new_signal
            prev_signal = new_signal
    
    # Histogram = MACD - Signal
    histogram = []
    for i in range(len(candles)):
        if macd_line[i] is None or signal_line[i] is None:
            histogram.append(None)
        else:
            histogram.append(macd_line[i] - signal_line[i])
    
    return {
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    }


def bollinger_bands(candles: List[Candle], period: int = 20, std_dev: float = 2.0) -> dict:
    """
    Calculate Bollinger Bands.
    
    Args:
        candles: List of Candle objects
        period: SMA period (default: 20)
        std_dev: Standard deviation multiplier (default: 2.0)
    
    Returns:
        Dict with 'upper', 'middle', 'lower' lists
    
    Example:
        >>> bb = bollinger_bands(candles)
        >>> if candles[-1].close < bb['lower'][-1]:
        ...     print("Price below lower band!")
    """
    middle = sma(candles, period)
    prices = [c.close for c in candles]
    
    upper = []
    lower = []
    
    for i in range(len(candles)):
        if middle[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            # Calculate standard deviation
            window = prices[max(0, i - period + 1):i + 1]
            mean = sum(window) / len(window)
            variance = sum((p - mean) ** 2 for p in window) / len(window)
            std = math.sqrt(variance)
            
            upper.append(middle[i] + std_dev * std)
            lower.append(middle[i] - std_dev * std)
    
    return {
        'upper': upper,
        'middle': middle,
        'lower': lower
    }


def stochastic(candles: List[Candle], k_period: int = 14, d_period: int = 3) -> dict:
    """
    Calculate Stochastic Oscillator.
    
    Args:
        candles: List of Candle objects
        k_period: %K period (default: 14)
        d_period: %D smoothing period (default: 3)
    
    Returns:
        Dict with 'k' and 'd' lists (0-100 range)
    
    Example:
        >>> stoch = stochastic(candles)
        >>> if stoch['k'][-1] < 20 and stoch['d'][-1] < 20:
        ...     print("Oversold!")
    """
    if len(candles) < k_period:
        return {'k': [None] * len(candles), 'd': [None] * len(candles)}
    
    k_values = [None] * (k_period - 1)
    
    for i in range(k_period - 1, len(candles)):
        window = candles[i - k_period + 1:i + 1]
        highest_high = max(c.high for c in window)
        lowest_low = min(c.low for c in window)
        
        if highest_high == lowest_low:
            k_values.append(50.0)  # Neutral if no range
        else:
            k = 100 * (candles[i].close - lowest_low) / (highest_high - lowest_low)
            k_values.append(k)
    
    # %D is SMA of %K
    d_values = [None] * (k_period + d_period - 2)
    for i in range(k_period + d_period - 2, len(candles)):
        window = k_values[i - d_period + 1:i + 1]
        if None not in window:
            d_values.append(sum(window) / d_period)
        else:
            d_values.append(None)
    
    return {'k': k_values, 'd': d_values}


def atr(candles: List[Candle], period: int = 14) -> List[float]:
    """
    Calculate Average True Range (volatility indicator).
    
    Args:
        candles: List of Candle objects
        period: ATR period (default: 14)
    
    Returns:
        List of ATR values
    """
    if len(candles) < 2:
        return [None] * len(candles)
    
    true_ranges = [candles[0].range]  # First TR is just the range
    
    for i in range(1, len(candles)):
        tr = max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i - 1].close),
            abs(candles[i].low - candles[i - 1].close)
        )
        true_ranges.append(tr)
    
    # ATR is EMA of true ranges
    result = [None] * (period - 1)
    
    # First ATR is simple average
    first_atr = sum(true_ranges[:period]) / period
    result.append(first_atr)
    
    # Subsequent ATRs use smoothing
    multiplier = 2 / (period + 1)
    for i in range(period, len(true_ranges)):
        new_atr = (true_ranges[i] - result[-1]) * multiplier + result[-1]
        result.append(new_atr)
    
    return result


def vwap(candles: List[Candle]) -> List[float]:
    """
    Calculate Volume-Weighted Average Price.
    
    Resets each day (assumes candles are continuous).
    
    Args:
        candles: List of Candle objects
    
    Returns:
        List of VWAP values
    """
    result = []
    cumulative_volume = 0
    cumulative_vp = 0
    last_day = None
    
    for candle in candles:
        current_day = candle.datetime.date()
        
        # Reset on new day
        if last_day is not None and current_day != last_day:
            cumulative_volume = 0
            cumulative_vp = 0
        
        typical_price = (candle.high + candle.low + candle.close) / 3
        cumulative_volume += candle.volume
        cumulative_vp += typical_price * candle.volume
        
        if cumulative_volume > 0:
            result.append(cumulative_vp / cumulative_volume)
        else:
            result.append(typical_price)
        
        last_day = current_day
    
    return result


# Convenience function to get the latest value
def latest(values: List[Optional[float]]) -> Optional[float]:
    """Get the most recent non-None value from an indicator list."""
    for v in reversed(values):
        if v is not None:
            return v
    return None
