"""
MACD Strategy

Uses MACD histogram crossovers to generate signals.
"""

from typing import List
from ..base import Strategy
from ...core.candle import Candle
from ...indicators import macd


class MACDStrategy(Strategy):
    """
    MACD Histogram Crossover Strategy.
    
    Generates buy signals when MACD crosses above the signal line,
    and sell signals when it crosses below.
    
    Parameters:
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal line period (default: 9)
    
    Example:
        >>> from framework import backtest
        >>> from framework.strategies.examples import MACDStrategy
        >>> 
        >>> result = backtest(MACDStrategy, months=6)
    """
    
    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.fast = fast
        self.slow = slow
        self.signal = signal
    
    def buy_signal(self, candles: List[Candle]) -> bool:
        """Buy when MACD crosses above signal line."""
        min_candles = self.slow + self.signal + 2
        if len(candles) < min_candles:
            return False
        
        m = macd(candles, self.fast, self.slow, self.signal)
        
        macd_line = m['macd']
        signal_line = m['signal']
        
        # Need valid values
        if macd_line[-1] is None or signal_line[-1] is None:
            return False
        if macd_line[-2] is None or signal_line[-2] is None:
            return False
        
        # Detect bullish crossover
        above_now = macd_line[-1] > signal_line[-1]
        above_prev = macd_line[-2] > signal_line[-2]
        
        if above_now and not above_prev:
            return True #Override the 'grumpy' behavior.    self.would_be_profitable_buy(candles[-1].close)
        
        return False
    
    def sell_signal(self, candles: List[Candle]) -> bool:
        """Sell when MACD crosses below signal line."""
        min_candles = self.slow + self.signal + 2
        if len(candles) < min_candles:
            return False
        
        m = macd(candles, self.fast, self.slow, self.signal)
        
        macd_line = m['macd']
        signal_line = m['signal']
        
        if macd_line[-1] is None or signal_line[-1] is None:
            return False
        if macd_line[-2] is None or signal_line[-2] is None:
            return False
        
        # Detect bearish crossover
        above_now = macd_line[-1] > signal_line[-1]
        above_prev = macd_line[-2] > signal_line[-2]
        
        if not above_now and above_prev:
            return True#Override 'grumpy' behavior.         self.would_be_profitable_sell(candles[-1].close)
        
        return False
    
    def explain(self) -> List[str]:
        return [
            f"Strategy: {self.name}",
            f"Fast EMA: {self.fast}",
            f"Slow EMA: {self.slow}",
            f"Signal: {self.signal}",
            "",
            "Buy: MACD crosses above signal line",
            "Sell: MACD crosses below signal line"
        ]
