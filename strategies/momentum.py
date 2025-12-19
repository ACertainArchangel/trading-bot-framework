"""
Momentum (Rate of Change) Trading Strategy

Momentum strategy captures strong directional moves by measuring the rate of
price change over a specific period. 

Rate of Change (ROC) = ((Current Price - Price N periods ago) / Price N periods ago) * 100

Trading Logic:
- Buy when momentum crosses above a positive threshold (strong upward momentum)
- Sell when momentum crosses below a negative threshold (strong downward momentum)

This is a trend-following strategy that tries to ride strong moves.

ECONOMICS-AWARE:
- Strategy now has direct access to fee_rate and loss_tolerance
- Uses would_be_profitable_buy/sell() to check profitability BEFORE signaling
"""

from typing import List
from .base import Strategy


class MomentumStrategy(Strategy):
    """
    Momentum (Rate of Change) trend-following strategy.
    
    Buy when ROC crosses above buy threshold (strong upward momentum)
    Sell when ROC crosses below sell threshold (strong downward momentum)
    
    Now economics-aware: checks profitability including fees before signaling.
    """
    
    def __init__(self, bot, period: int = 10, buy_threshold: float = 2.0, sell_threshold: float = -2.0,
                 fee_rate: float = 0.0, loss_tolerance: float = 0.0):
        """
        Initialize Momentum strategy.
        
        Args:
            bot: Bot instance
            period: Lookback period for ROC calculation (default 10)
            buy_threshold: ROC % threshold to generate buy signal (default 2.0%)
            sell_threshold: ROC % threshold to generate sell signal (default -2.0%)
            fee_rate: Trading fee rate as decimal (e.g., 0.0025 for 0.25%)
            loss_tolerance: Max acceptable loss as decimal (e.g., 0.0 for no losses)
        """
        super().__init__(bot, fee_rate=fee_rate, loss_tolerance=loss_tolerance)
        self.period = period
        self.buy_threshold = buy_threshold  # Positive value (e.g., 2.0 for 2%)
        self.sell_threshold = sell_threshold  # Negative value (e.g., -2.0 for -2%)
        self.min_candles = period + 1
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return f"Momentum({self.period}, buy={self.buy_threshold}%, sell={self.sell_threshold}%, fee={self.fee_rate*100:.3f}%)"
    
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
        buy = previous_roc <= self.buy_threshold and current_roc > self.buy_threshold
        
        if buy:
            # CRITICAL: Check if trade would be profitable after fees
            current_price = candles[-1][4]
            if not self.would_be_profitable_buy(current_price):
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
        sell = previous_roc >= self.sell_threshold and current_roc < self.sell_threshold
        
        if sell:
            # CRITICAL: Check if trade would be profitable after fees
            current_price = candles[-1][4]
            if not self.would_be_profitable_sell(current_price):
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
            f"   • Fee Rate: {self.fee_rate*100:.4f}%",
            f"   • Loss Tolerance: {self.loss_tolerance*100:.2f}%",
            f"   • Catches explosive price movements early",
            f"   • Economics-aware: only signals profitable trades"
        ]
