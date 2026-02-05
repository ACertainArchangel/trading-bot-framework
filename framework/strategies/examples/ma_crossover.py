"""
Moving Average Crossover Strategy

Classic strategy that buys when a fast MA crosses above a slow MA,
and sells when it crosses below.
"""

from typing import List
from ..base import Strategy
from ...core.candle import Candle
from ...indicators import ema


class MACrossover(Strategy):
    """
    Moving Average Crossover Strategy.
    
    Generates buy signals when a fast EMA crosses above a slow EMA,
    and sell signals when it crosses below.
    
    Parameters:
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
    
    Example:
        >>> from framework import backtest
        >>> from framework.strategies.examples import MACrossover
        >>> 
        >>> result = backtest(MACrossover, months=6, strategy_params={
        ...     'fast_period': 9,
        ...     'slow_period': 21
        ... })
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period
        
        # Track previous state for crossover detection
        self._prev_fast_above = None
    
    def buy_signal(self, candles: List[Candle]) -> bool:
        """Buy when fast EMA crosses above slow EMA."""
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        
        # Need valid values
        if fast[-1] is None or slow[-1] is None:
            return False
        if fast[-2] is None or slow[-2] is None:
            return False
        
        # Detect crossover
        fast_above_now = fast[-1] > slow[-1]
        fast_above_prev = fast[-2] > slow[-2]
        
        # Buy on bullish crossover
        if fast_above_now and not fast_above_prev:
            return True #Override the 'grumpy' behavior.    self.would_be_profitable_buy(candles[-1].close)
        
        return False
    
    def sell_signal(self, candles: List[Candle]) -> bool:
        """Sell when fast EMA crosses below slow EMA."""
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        
        if fast[-1] is None or slow[-1] is None:
            return False
        if fast[-2] is None or slow[-2] is None:
            return False
        
        # Detect crossover
        fast_above_now = fast[-1] > slow[-1]
        fast_above_prev = fast[-2] > slow[-2]
        
        # Sell on bearish crossover
        if not fast_above_now and fast_above_prev:
            return True#Override 'grumpy' behavior.         self.would_be_profitable_sell(candles[-1].close)
        
        return False
    
    def explain(self) -> List[str]:
        return [
            f"Strategy: {self.name}",
            f"Fast EMA: {self.fast_period}",
            f"Slow EMA: {self.slow_period}",
            "",
            "Buy: Fast EMA crosses above Slow EMA",
            "Sell: Fast EMA crosses below Slow EMA"
        ]
