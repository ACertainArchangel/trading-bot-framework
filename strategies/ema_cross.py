"""
EMA (Exponential Moving Average) Crossover Strategy

Simple and effective trend-following strategy using two EMAs:
- Fast EMA (shorter period) - more responsive to recent prices
- Slow EMA (longer period) - smoother, captures longer trends

Trading Logic:
- Buy when fast EMA crosses above slow EMA (golden cross - bullish)
- Sell when fast EMA crosses below slow EMA (death cross - bearish)
"""

from typing import List
from .base import Strategy


class EMACrossStrategy(Strategy):
    """
    EMA crossover trend-following strategy.
    
    Buy when fast EMA crosses above slow EMA
    Sell when fast EMA crosses below slow EMA
    """
    
    def __init__(self, bot, fast: int = 9, slow: int = 21):
        """
        Initialize EMA crossover strategy.
        
        Args:
            bot: Bot instance
            fast: Fast EMA period (default 9)
            slow: Slow EMA period (default 21)
        """
        super().__init__(bot)
        self.fast = fast
        self.slow = slow
        self.min_candles = slow + 1
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return f"EMA_Cross({self.fast}/{self.slow})"
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average.
        
        Args:
            prices: List of closing prices
            period: EMA period
            
        Returns:
            EMA value
        """
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        
        # Calculate multiplier
        multiplier = 2 / (period + 1)
        
        # Start with SMA for first EMA value
        ema = sum(prices[:period]) / period
        
        # Calculate EMA for remaining prices
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal when fast EMA crosses above slow EMA.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles:
            return False
        
        # Extract closing prices
        closes = [candle[4] for candle in candles]
        
        # Calculate current EMAs
        fast_ema = self.calculate_ema(closes, self.fast)
        slow_ema = self.calculate_ema(closes, self.slow)
        
        # Calculate previous EMAs (without last candle)
        prev_fast_ema = self.calculate_ema(closes[:-1], self.fast)
        prev_slow_ema = self.calculate_ema(closes[:-1], self.slow)
        
        # Buy when fast EMA crosses above slow EMA (golden cross)
        # Previous: fast was below or equal to slow
        # Current: fast is above slow
        buy = prev_fast_ema <= prev_slow_ema and fast_ema > slow_ema
        
        if buy:
            # CRITICAL: Check if trade would be profitable after fees
            current_price = candles[-1][4]
            if not self.would_be_profitable_buy(current_price):
                return False
        
        return buy
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal when fast EMA crosses below slow EMA.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles:
            return False
        
        # Extract closing prices
        closes = [candle[4] for candle in candles]
        
        # Calculate current EMAs
        fast_ema = self.calculate_ema(closes, self.fast)
        slow_ema = self.calculate_ema(closes, self.slow)
        
        # Calculate previous EMAs (without last candle)
        prev_fast_ema = self.calculate_ema(closes[:-1], self.fast)
        prev_slow_ema = self.calculate_ema(closes[:-1], self.slow)
        
        # Sell when fast EMA crosses below slow EMA (death cross)
        # Previous: fast was above or equal to slow
        # Current: fast is below slow
        sell = prev_fast_ema >= prev_slow_ema and fast_ema < slow_ema
        
        if sell:
            # CRITICAL: Check if trade would be profitable after fees
            current_price = candles[-1][4]
            if not self.would_be_profitable_sell(current_price):
                return False
        
        return sell
    
    @property
    def name(self):
        """Return strategy name."""
        return f"EMA Cross ({self.fast}/{self.slow})"
    
    def explain(self) -> List[str]:
        """Provide explanation of the strategy."""
        return [
            f"🔄 EMA Crossover Strategy (EMA {self.fast}/{self.slow})",
            f"   • Golden Cross: BUY when EMA({self.fast}) crosses above EMA({self.slow})",
            f"   • Death Cross: SELL when EMA({self.fast}) crosses below EMA({self.slow})",
            f"   • Trend-following strategy that catches major price movements",
            f"   • Fast EMA ({self.fast}) reacts quickly to price changes",
            f"   • Slow EMA ({self.slow}) smooths out long-term trends",
            f"   • Baseline protection ensures we never take a loss"
        ]
