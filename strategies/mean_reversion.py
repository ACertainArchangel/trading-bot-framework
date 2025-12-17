"""
Mean Reversion Trading Strategy

Mean reversion is based on the idea that prices tend to return to their average over time.
When price deviates significantly from the mean, it's likely to revert back.

Trading Logic:
- Buy when price drops significantly below the moving average (oversold)
- Sell when price rises significantly above the moving average (overbought)

The strategy uses standard deviations to measure "significant" deviation.
"""

from typing import List
from .base import Strategy
import statistics


class MeanReversionStrategy(Strategy):
    """
    Mean reversion strategy using moving average and standard deviation.
    
    Buy when price is N standard deviations below the mean
    Sell when price is N standard deviations above the mean
    """
    
    def __init__(self, bot, period: int = 20, buy_threshold: float = -1.5, sell_threshold: float = 1.5):
        """
        Initialize Mean Reversion strategy.
        
        Args:
            bot: Bot instance
            period: Moving average period (default 20)
            buy_threshold: Number of std devs below mean to buy (default -1.5)
            sell_threshold: Number of std devs above mean to sell (default 1.5)
        """
        super().__init__(bot)
        self.period = period
        self.buy_threshold = buy_threshold  # Negative value (e.g., -1.5)
        self.sell_threshold = sell_threshold  # Positive value (e.g., 1.5)
        self.min_candles = period + 1
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return f"MeanReversion({self.period}, buy={self.buy_threshold}σ, sell={self.sell_threshold}σ)"
    
    def calculate_zscore(self, prices: List[float]) -> float:
        """
        Calculate z-score (number of standard deviations from mean).
        z-score = (current_price - mean) / std_dev
        
        Args:
            prices: List of closing prices
            
        Returns:
            Z-score value
        """
        if len(prices) < self.period:
            return 0.0
        
        # Get recent prices
        recent_prices = prices[-self.period:]
        
        # Calculate mean and standard deviation
        mean = sum(recent_prices) / self.period
        std = statistics.stdev(recent_prices)
        
        # Avoid division by zero
        if std == 0:
            return 0.0
        
        # Calculate z-score for current price
        current_price = prices[-1]
        zscore = (current_price - mean) / std
        
        return zscore
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal when price is significantly below mean (oversold).
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles:
            return False
        
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Calculate current z-score (use cached closes)
        current_zscore = self.calculate_zscore(self._closes_cache)
        
        # Calculate previous z-score
        previous_zscore = self.calculate_zscore(self._closes_cache[:-1])
        
        # Buy when z-score crosses below buy threshold (price drops below mean)
        # Previous: z-score was above or equal to threshold
        # Current: z-score is below threshold
        buy = previous_zscore >= self.buy_threshold and current_zscore < self.buy_threshold
        
        if buy:
            # Check baseline protection before signaling buy
            current_price = candles[-1][4]
            if not self.check_baseline_for_buy(current_price):
                return False
        
        return buy
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal when price is significantly above mean (overbought).
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles:
            return False
        
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Calculate current z-score (use cached closes)
        current_zscore = self.calculate_zscore(self._closes_cache)
        
        # Calculate previous z-score
        previous_zscore = self.calculate_zscore(self._closes_cache[:-1])
        
        # Sell when z-score crosses above sell threshold (price rises above mean)
        # Previous: z-score was below or equal to threshold
        # Current: z-score is above threshold
        sell = previous_zscore <= self.sell_threshold and current_zscore > self.sell_threshold
        
        if sell:
            # Check baseline protection before signaling sell
            current_price = candles[-1][4]
            if not self.check_baseline_for_sell(current_price):
                return False
        
        return sell
