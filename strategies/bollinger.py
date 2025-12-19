"""
Bollinger Bands Trading Strategy

Bollinger Bands consist of a middle band (SMA) and two outer bands at ±N standard deviations.
The bands expand and contract based on volatility.

Trading Logic:
- Buy when price touches or crosses below the lower band (oversold)
- Sell when price touches or crosses above the upper band (overbought)
"""

from typing import List
from .base import Strategy
import statistics


class BollingerStrategy(Strategy):
    """
    Bollinger Bands mean reversion strategy.
    
    Buy when price crosses below lower band (oversold condition)
    Sell when price crosses above upper band (overbought condition)
    """
    
    def __init__(self, bot, period: int = 20, std_dev: float = 2.0):
        """
        Initialize Bollinger Bands strategy.
        
        Args:
            bot: Bot instance
            period: Moving average period (default 20)
            std_dev: Number of standard deviations for bands (default 2.0)
        """
        super().__init__(bot)
        self.period = period
        self.std_dev = std_dev
        self.min_candles = period
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return f"Bollinger({self.period}, {self.std_dev}σ)"
    
    def calculate_bands(self, prices: List[float]) -> tuple:
        """
        Calculate Bollinger Bands.
        
        Args:
            prices: List of closing prices
            
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        if len(prices) < self.period:
            return (None, None, None)
        
        # Get recent prices for calculation
        recent_prices = prices[-self.period:]
        
        # Calculate middle band (SMA)
        middle_band = sum(recent_prices) / self.period
        
        # Calculate standard deviation
        std = statistics.stdev(recent_prices)
        
        # Calculate upper and lower bands
        upper_band = middle_band + (self.std_dev * std)
        lower_band = middle_band - (self.std_dev * std)
        
        return (upper_band, middle_band, lower_band)
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal when price crosses below lower Bollinger Band.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            return False
        
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Calculate current and previous bands (use cached closes)
        current_upper, current_middle, current_lower = self.calculate_bands(self._closes_cache)
        prev_upper, prev_middle, prev_lower = self.calculate_bands(self._closes_cache[:-1])
        
        if current_lower is None or prev_lower is None:
            return False
        
        current_price = self._closes_cache[-1]
        previous_price = self._closes_cache[-2]
        
        # Buy when price crosses from above to below lower band
        # (was above lower band, now at or below)
        buy = previous_price > prev_lower and current_price <= current_lower
        
        if buy:
            # CRITICAL: Check if trade would be profitable after fees
            if not self.would_be_profitable_buy(current_price):
                return False
        
        return buy
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal when price crosses above upper Bollinger Band.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            return False
        
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Calculate current and previous bands (use cached closes)
        current_upper, current_middle, current_lower = self.calculate_bands(self._closes_cache)
        prev_upper, prev_middle, prev_lower = self.calculate_bands(self._closes_cache[:-1])
        
        if current_upper is None or prev_upper is None:
            return False
        
        current_price = self._closes_cache[-1]
        previous_price = self._closes_cache[-2]
        
        # Sell when price crosses from below to above upper band
        # (was below upper band, now at or above)
        sell = previous_price < prev_upper and current_price >= current_upper
        
        if sell:
            # CRITICAL: Check if trade would be profitable after fees
            if not self.would_be_profitable_sell(current_price):
                return False
        
        return sell

    def name(self) -> str:
        return "Bollinger Bands Strategy"