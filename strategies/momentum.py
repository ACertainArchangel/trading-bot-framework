"""
Momentum (Rate of Change) Trading Strategy

Momentum strategy captures strong directional moves by measuring the rate of
price change over a specific period. 

Rate of Change (ROC) = ((Current Price - Price N periods ago) / Price N periods ago) * 100

Trading Logic:
- Buy when momentum crosses above a positive threshold (strong upward momentum)
- Sell when momentum crosses below a negative threshold (strong downward momentum)

This is a trend-following strategy that tries to ride strong moves.
"""

from typing import List
from .base import Strategy


class MomentumStrategy(Strategy):
    """
    Momentum (Rate of Change) trend-following strategy.
    
    Buy when ROC crosses above buy threshold (strong upward momentum)
    Sell when ROC crosses below sell threshold (strong downward momentum)
    """
    
    def __init__(self, bot, period: int = 10, buy_threshold: float = 2.0, sell_threshold: float = -2.0):
        """
        Initialize Momentum strategy.
        
        Args:
            bot: Bot instance
            period: Lookback period for ROC calculation (default 10)
            buy_threshold: ROC % threshold to generate buy signal (default 2.0%)
            sell_threshold: ROC % threshold to generate sell signal (default -2.0%)
        """
        super().__init__(bot)
        self.period = period
        self.buy_threshold = buy_threshold  # Positive value (e.g., 2.0 for 2%)
        self.sell_threshold = sell_threshold  # Negative value (e.g., -2.0 for -2%)
        self.min_candles = period + 1
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return f"Momentum({self.period}, buy={self.buy_threshold}%, sell={self.sell_threshold}%)"
    
    def calculate_roc(self, prices: List[float]) -> float:
        """
        Calculate Rate of Change (ROC) as a percentage.
        ROC = ((Current - Old) / Old) * 100
        
        Args:
            prices: List of closing prices
            
        Returns:
            ROC percentage
        """
        if len(prices) < self.period + 1:
            return 0.0
        
        current_price = prices[-1]
        old_price = prices[-(self.period + 1)]
        
        # Avoid division by zero
        if old_price == 0:
            return 0.0
        
        roc = ((current_price - old_price) / old_price) * 100
        return roc
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal when momentum crosses above buy threshold.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            return False
        
        # Extract closing prices
        closes = [candle[4] for candle in candles]
        
        # Calculate current ROC
        current_roc = self.calculate_roc(closes)
        
        # Calculate previous ROC
        previous_roc = self.calculate_roc(closes[:-1])
        
        # Buy when ROC crosses above buy threshold (momentum turning positive)
        # Previous: ROC was below or equal to threshold
        # Current: ROC is above threshold
        buy = previous_roc <= self.buy_threshold and current_roc > self.buy_threshold
        
        if buy:
            # Check baseline protection before signaling buy
            current_price = candles[-1][4]
            if not self.check_baseline_for_buy(current_price):
                return False
        
        return buy
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal when momentum crosses below sell threshold.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            return False
        
        # Extract closing prices
        closes = [candle[4] for candle in candles]
        
        # Calculate current ROC
        current_roc = self.calculate_roc(closes)
        
        # Calculate previous ROC
        previous_roc = self.calculate_roc(closes[:-1])
        
        # Sell when ROC crosses below sell threshold (momentum turning negative)
        # Previous: ROC was above or equal to threshold
        # Current: ROC is below threshold
        sell = previous_roc >= self.sell_threshold and current_roc < self.sell_threshold
        
        if sell:
            # Check baseline protection before signaling sell
            current_price = candles[-1][4]
            if not self.check_baseline_for_sell(current_price):
                return False
        
        return sell
    
    @property
    def name(self):
        """Return strategy name."""
        return f"Momentum (ROC {self.period})"
    
    def explain(self) -> List[str]:
        """Provide explanation of the strategy."""
        return [
            f"⚡ Momentum Strategy (ROC {self.period}-period)",
            f"   • Calculates Rate of Change (ROC) over {self.period} candles",
            f"   • ROC = ((Current Price - Old Price) / Old Price) × 100",
            f"   • BUY when ROC crosses above {self.buy_threshold}% (strong upward momentum)",
            f"   • SELL when ROC crosses below {self.sell_threshold}% (strong downward momentum)",
            f"   • Catches explosive price movements early",
            f"   • Baseline protection ensures we never take a loss"
        ]
