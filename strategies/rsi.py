"""
RSI (Relative Strength Index) Trading Strategy

RSI is a momentum oscillator that measures the speed and magnitude of price changes.
It oscillates between 0 and 100, with traditional levels:
- Above 70: Overbought (potential sell signal)
- Below 30: Oversold (potential buy signal)
"""

from typing import List
from .base import Strategy


class RSIStrategy(Strategy):
    """
    RSI (Relative Strength Index) trading strategy.
    
    Buy when RSI crosses above oversold level (default 30)
    Sell when RSI crosses above overbought level (default 70)
    """
    
    def __init__(self, bot, period: int = 14, oversold: int = 30, overbought: int = 70):
        """
        Initialize RSI strategy.
        
        Args:
            bot: Bot instance
            period: RSI calculation period (default 14)
            oversold: Oversold threshold for buy signals (default 30)
            overbought: Overbought threshold for sell signals (default 70)
        """
        super().__init__(bot)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.min_candles = period + 1
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return f"RSI({self.period}, oversold={self.oversold}, overbought={self.overbought})"
    
    def calculate_rsi(self, prices: List[float]) -> float:
        """
        Calculate RSI using the traditional method.
        
        Args:
            prices: List of closing prices
            
        Returns:
            RSI value (0-100)
        """
        if len(prices) < self.period + 1:
            return 50.0  # Neutral RSI if not enough data
        
        # Calculate price changes
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        
        # Calculate average gain and loss over period
        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period
        
        # Avoid division by zero
        if avg_loss == 0:
            return 100.0
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal when RSI crosses above oversold level.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles:
            return False
        
        # Extract closing prices
        closes = [candle[4] for candle in candles]
        
        # Calculate current and previous RSI
        current_rsi = self.calculate_rsi(closes)
        previous_rsi = self.calculate_rsi(closes[:-1])
        
        # Buy when RSI crosses above oversold level (was below, now above)
        buy = previous_rsi <= self.oversold and current_rsi > self.oversold
        
        if buy:
            # Check baseline protection before signaling buy
            current_price = candles[-1][4]
            if not self.check_baseline_for_buy(current_price):
                return False
        
        return buy
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal when RSI crosses above overbought level.
        
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
        
        # Calculate current and previous RSI (use cached closes)
        current_rsi = self.calculate_rsi(self._closes_cache)
        previous_rsi = self.calculate_rsi(self._closes_cache[:-1])
        
        # Sell when RSI crosses above overbought level (was below, now above or at)
        sell = previous_rsi < self.overbought and current_rsi >= self.overbought
        
        if sell:
            # Check baseline protection before signaling sell
            current_price = candles[-1][4]
            if not self.check_baseline_for_sell(current_price):
                return False
        
        return sell
