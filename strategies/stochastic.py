"""
Stochastic Oscillator Trading Strategy

The Stochastic Oscillator is a momentum indicator that compares a closing price
to its price range over a given time period.

Components:
- %K line: Fast stochastic (main line)
- %D line: Slow stochastic (moving average of %K, signal line)

Values range from 0 to 100:
- Above 80: Overbought
- Below 20: Oversold

Trading Logic:
- Buy when %K crosses above %D in oversold territory (< 20)
- Sell when %K crosses below %D in overbought territory (> 80)
"""

from typing import List
from .base import Strategy


class StochasticStrategy(Strategy):
    """
    Stochastic Oscillator momentum strategy.
    
    Buy when %K crosses above %D while oversold
    Sell when %K crosses below %D while overbought
    """
    
    def __init__(self, bot, k_period: int = 14, d_period: int = 3, oversold: int = 20, overbought: int = 80):
        """
        Initialize Stochastic strategy.
        
        Args:
            bot: Bot instance
            k_period: %K period (default 14)
            d_period: %D smoothing period (default 3)
            oversold: Oversold threshold (default 20)
            overbought: Overbought threshold (default 80)
        """
        super().__init__(bot)
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.min_candles = k_period + d_period
        
    def __str__(self):
        return f"Stochastic({self.k_period},{self.d_period})"
    
    def calculate_stochastic_k(self, candles: List) -> float:
        """
        Calculate %K (fast stochastic).
        %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
        
        Args:
            candles: Recent candles for calculation
            
        Returns:
            %K value (0-100)
        """
        if len(candles) < self.k_period:
            return 50.0
        
        # Get recent candles
        recent = candles[-self.k_period:]
        
        # Extract highs, lows, and current close
        highs = [c[2] for c in recent]  # High prices
        lows = [c[1] for c in recent]   # Low prices
        current_close = candles[-1][4]
        
        highest_high = max(highs)
        lowest_low = min(lows)
        
        # Avoid division by zero
        if highest_high == lowest_low:
            return 50.0
        
        k = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
        return k
    
    def calculate_stochastic_d(self, k_values: List[float]) -> float:
        """
        Calculate %D (slow stochastic - SMA of %K).
        
        Args:
            k_values: List of recent %K values
            
        Returns:
            %D value (0-100)
        """
        if len(k_values) < self.d_period:
            return sum(k_values) / len(k_values) if k_values else 50.0
        
        recent_k = k_values[-self.d_period:]
        return sum(recent_k) / self.d_period
    
    def get_k_values(self, candles: List, num_values: int) -> List[float]:
        """
        Calculate multiple %K values for %D calculation.
        
        Args:
            candles: Historical candle data
            num_values: Number of %K values to calculate
            
        Returns:
            List of %K values
        """
        k_values = []
        for i in range(len(candles) - num_values + 1, len(candles) + 1):
            if i >= self.k_period:
                k = self.calculate_stochastic_k(candles[:i])
                k_values.append(k)
        return k_values
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal when %K crosses above %D in oversold territory.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            return False
        
        # Calculate current %K and %D
        k_values = self.get_k_values(candles, self.d_period + 1)
        if len(k_values) < self.d_period + 1:
            return False
        
        current_k = k_values[-1]
        current_d = self.calculate_stochastic_d(k_values)
        
        # Calculate previous %K and %D
        prev_k = k_values[-2]
        prev_d = self.calculate_stochastic_d(k_values[:-1])
        
        # Buy when %K crosses above %D while in oversold territory
        # Previous: %K was below or equal to %D
        # Current: %K is above %D
        # Condition: Both are in oversold territory (< oversold threshold)
        buy = (prev_k <= prev_d and current_k > current_d and 
               current_k < self.oversold and current_d < self.oversold)
        
        if buy:
            # Check baseline protection before signaling buy
            current_price = candles[-1][4]
            if not self.check_baseline_for_buy(current_price):
                return False
        
        return buy
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal when %K crosses below %D in overbought territory.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            return False
        
        # Calculate current %K and %D
        k_values = self.get_k_values(candles, self.d_period + 1)
        if len(k_values) < self.d_period + 1:
            return False
        
        current_k = k_values[-1]
        current_d = self.calculate_stochastic_d(k_values)
        
        # Calculate previous %K and %D
        prev_k = k_values[-2]
        prev_d = self.calculate_stochastic_d(k_values[:-1])
        
        # Sell when %K crosses below %D while in overbought territory
        # Previous: %K was above or equal to %D
        # Current: %K is below %D
        # Condition: Both are in overbought territory (> overbought threshold)
        sell = (prev_k >= prev_d and current_k < current_d and 
                current_k > self.overbought and current_d > self.overbought)
        
        if sell:
            # Check baseline protection before signaling sell
            current_price = candles[-1][4]
            if not self.check_baseline_for_sell(current_price):
                return False
        
        return sell
