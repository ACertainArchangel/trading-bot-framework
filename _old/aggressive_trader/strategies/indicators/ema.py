"""
Exponential Moving Average (EMA) Indicator.

EMA gives more weight to recent prices, making it more responsive to new information
than a Simple Moving Average (SMA).

Formula: EMA = Price(t) × k + EMA(y) × (1 − k)
Where: k = 2 ÷ (N + 1), N = period
"""

from typing import List, Optional


class EMAIndicator:
    """
    Exponential Moving Average calculator.
    """
    
    def __init__(self, period: int = 20):
        """
        Initialize EMA with specified period.
        
        Args:
            period: Number of periods for EMA calculation
        """
        self.period = period
        self.multiplier = 2 / (period + 1)
    
    def calculate(self, values: List[float]) -> Optional[List[float]]:
        """
        Calculate EMA for a series of values.
        
        Args:
            values: List of prices/values (most recent last)
            
        Returns:
            List of EMA values aligned with input (starts from index period-1)
            Returns None if insufficient data
        """
        if len(values) < self.period:
            return None
        
        ema_values = []
        
        # First EMA value is SMA of first 'period' values
        sma = sum(values[:self.period]) / self.period
        ema_values.append(sma)
        
        # Calculate EMA for remaining values
        for i in range(self.period, len(values)):
            ema = (values[i] * self.multiplier) + (ema_values[-1] * (1 - self.multiplier))
            ema_values.append(ema)
        
        return ema_values
    
    def calculate_single(self, values: List[float]) -> Optional[float]:
        """
        Calculate only the current (most recent) EMA value.
        
        Args:
            values: List of prices/values (most recent last)
            
        Returns:
            Current EMA value, or None if insufficient data
        """
        ema_values = self.calculate(values)
        return ema_values[-1] if ema_values else None
    
    def get_slope(self, values: List[float], lookback: int = 3) -> Optional[float]:
        """
        Calculate the slope of the EMA over recent periods.
        
        Args:
            values: List of prices/values
            lookback: Number of periods to calculate slope over
            
        Returns:
            Slope as percentage change, or None if insufficient data
        """
        ema_values = self.calculate(values)
        if not ema_values or len(ema_values) < lookback:
            return None
        
        recent_ema = ema_values[-lookback:]
        slope = (recent_ema[-1] - recent_ema[0]) / recent_ema[0]
        
        return slope
    
    def is_price_above(self, values: List[float]) -> Optional[bool]:
        """
        Check if current price is above the EMA.
        
        Args:
            values: List of prices (most recent last)
            
        Returns:
            True if price > EMA, False otherwise, None if insufficient data
        """
        current_ema = self.calculate_single(values)
        if current_ema is None:
            return None
        
        return values[-1] > current_ema
    
    def distance_from_ema(self, values: List[float]) -> Optional[float]:
        """
        Calculate the percentage distance from current price to EMA.
        
        Args:
            values: List of prices (most recent last)
            
        Returns:
            Percentage distance (positive = above, negative = below)
            None if insufficient data
        """
        current_ema = self.calculate_single(values)
        if current_ema is None or current_ema == 0:
            return None
        
        current_price = values[-1]
        distance = (current_price - current_ema) / current_ema
        
        return distance


def detect_ema_crossover(short_ema_values: List[float], long_ema_values: List[float]) -> dict:
    """
    Detect crossovers between two EMA series.
    
    Args:
        short_ema_values: Shorter period EMA values
        long_ema_values: Longer period EMA values
        
    Returns:
        Dictionary with:
            - 'golden_cross': True if short just crossed above long
            - 'death_cross': True if short just crossed below long
            - 'trend_bullish': True if short > long currently
    """
    if not short_ema_values or not long_ema_values:
        return {
            'golden_cross': False,
            'death_cross': False,
            'trend_bullish': False
        }
    
    # Align lengths (use shorter length)
    min_len = min(len(short_ema_values), len(long_ema_values))
    if min_len < 2:
        return {
            'golden_cross': False,
            'death_cross': False,
            'trend_bullish': short_ema_values[-1] > long_ema_values[-1] if min_len == 1 else False
        }
    
    short = short_ema_values[-min_len:]
    long = long_ema_values[-min_len:]
    
    # Current state
    current_short = short[-1]
    current_long = long[-1]
    prev_short = short[-2]
    prev_long = long[-2]
    
    # Detect crossovers
    golden_cross = prev_short <= prev_long and current_short > current_long
    death_cross = prev_short >= prev_long and current_short < current_long
    trend_bullish = current_short > current_long
    
    return {
        'golden_cross': golden_cross,
        'death_cross': death_cross,
        'trend_bullish': trend_bullish
    }
