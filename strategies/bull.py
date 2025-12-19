"""
Bull Strategy - Always stays LONG (buy signal only)

This is a test strategy that always returns True for buy signals
and False for sell signals. Used for testing order execution.

ECONOMICS-AWARE:
- Strategy now has direct access to fee_rate and loss_tolerance
- For testing purposes, this strategy ignores economics checks
"""

from strategies import Strategy


class BullStrategy(Strategy):
    """
    Bull Strategy - Always buy, never sell
    
    This strategy is designed for testing purposes only.
    It will buy BTC and hold it indefinitely.
    """
    
    def __init__(self, bot, fee_rate: float = 0.0, loss_tolerance: float = 0.0):
        super().__init__(bot, fee_rate=fee_rate, loss_tolerance=loss_tolerance)
        self.name = "Bull"
    
    def buy_signal(self, candles: list) -> bool:
        """
        Always return True to buy BTC
        """
        return True
    
    def sell_signal(self, candles: list) -> bool:
        """
        Never sell - always stay LONG
        """
        return False
