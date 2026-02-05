"""
MACD (Moving Average Convergence Divergence) Indicator.

MACD consists of:
- MACD Line: Fast EMA - Slow EMA
- Signal Line: EMA of MACD Line
- Histogram: MACD Line - Signal Line

Crossovers:
- Bullish: MACD crosses above Signal line
- Bearish: MACD crosses below Signal line
"""

from typing import List, Dict, Optional


class MACDIndicator:
    """
    MACD indicator with crossover detection.
    """
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        """
        Initialize MACD with configurable periods.
        
        Args:
            fast_period: Period for fast EMA (default 12)
            slow_period: Period for slow EMA (default 26)
            signal_period: Period for signal line EMA (default 9)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
    
    def _calculate_ema(self, values: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average.
        
        Args:
            values: Price data
            period: EMA period
            
        Returns:
            List of EMA values (same length as input, with NaN-equivalent for initial values)
        """
        if len(values) < period:
            return []
        
        ema_values = []
        multiplier = 2 / (period + 1)
        
        # First EMA value is SMA
        sma = sum(values[:period]) / period
        ema_values.append(sma)
        
        # Calculate EMA for remaining values
        for i in range(period, len(values)):
            ema = (values[i] * multiplier) + (ema_values[-1] * (1 - multiplier))
            ema_values.append(ema)
        
        return ema_values
    
    def calculate(self, closes: List[float]) -> Optional[Dict]:
        """
        Calculate MACD values and detect crossovers.
        
        Args:
            closes: List of closing prices (most recent last)
            
        Returns:
            Dictionary with:
                - 'macd_line': Current MACD line value
                - 'signal_line': Current signal line value
                - 'histogram': Current histogram value (MACD - Signal)
                - 'bullish_cross': True if MACD just crossed above signal
                - 'bearish_cross': True if MACD just crossed below signal
                - 'macd_values': Full MACD line history
                - 'signal_values': Full signal line history
                - 'histogram_values': Full histogram history
            Returns None if insufficient data
        """
        min_periods = self.slow_period + self.signal_period
        if len(closes) < min_periods:
            return None
        
        # Calculate fast and slow EMAs
        fast_ema = self._calculate_ema(closes, self.fast_period)
        slow_ema = self._calculate_ema(closes, self.slow_period)
        
        if not fast_ema or not slow_ema:
            return None
        
        # Align EMAs - slow EMA starts later
        offset = self.slow_period - self.fast_period
        fast_ema_aligned = fast_ema[offset:]
        
        # Calculate MACD line
        macd_line = [f - s for f, s in zip(fast_ema_aligned, slow_ema)]
        
        if len(macd_line) < self.signal_period:
            return None
        
        # Calculate signal line (EMA of MACD)
        signal_line = self._calculate_ema(macd_line, self.signal_period)
        
        if not signal_line or len(signal_line) < 2:
            return None
        
        # Align MACD with signal line
        signal_offset = self.signal_period - 1
        macd_aligned = macd_line[signal_offset:]
        
        # Calculate histogram
        histogram = [m - s for m, s in zip(macd_aligned, signal_line)]
        
        if len(histogram) < 2:
            return None
        
        # Current values
        current_macd = macd_aligned[-1]
        current_signal = signal_line[-1]
        current_histogram = histogram[-1]
        
        # Previous values for crossover detection
        prev_macd = macd_aligned[-2]
        prev_signal = signal_line[-2]
        
        # Detect crossovers
        bullish_cross = prev_macd <= prev_signal and current_macd > current_signal
        bearish_cross = prev_macd >= prev_signal and current_macd < current_signal
        
        return {
            'macd_line': current_macd,
            'signal_line': current_signal,
            'histogram': current_histogram,
            'bullish_cross': bullish_cross,
            'bearish_cross': bearish_cross,
            'macd_values': macd_aligned,
            'signal_values': signal_line,
            'histogram_values': histogram
        }
    
    def get_trend_strength(self, closes: List[float]) -> Optional[float]:
        """
        Get trend strength based on histogram momentum.
        
        Returns:
            Float between -1 (strong bearish) and 1 (strong bullish)
            None if insufficient data
        """
        result = self.calculate(closes)
        if not result or len(result['histogram_values']) < 5:
            return None
        
        histogram = result['histogram_values']
        
        # Look at recent histogram trend
        recent = histogram[-5:]
        avg_histogram = sum(recent) / len(recent)
        
        # Normalize to roughly -1 to 1 range
        # Use current price as reference for scaling
        price_scale = closes[-1] * 0.01  # 1% of price
        normalized = max(-1, min(1, avg_histogram / price_scale))
        
        return normalized
