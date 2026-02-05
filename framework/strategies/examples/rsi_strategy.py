"""
RSI (Relative Strength Index) Strategy

Buys when RSI indicates oversold conditions (< 30),
sells when RSI indicates overbought conditions (> 70).
"""

from typing import List
from ..base import Strategy
from ...core.candle import Candle
from ...indicators import rsi


class RSIStrategy(Strategy):
    """
    RSI Overbought/Oversold Strategy.
    
    Generates buy signals when RSI drops below the oversold threshold,
    and sell signals when RSI rises above the overbought threshold.
    
    Parameters:
        period: RSI calculation period (default: 14)
        oversold: Oversold threshold (default: 30)
        overbought: Overbought threshold (default: 70)
    
    Example:
        >>> from framework import backtest
        >>> from framework.strategies.examples import RSIStrategy
        >>> 
        >>> result = backtest(RSIStrategy, months=6, strategy_params={
        ...     'oversold': 25,
        ...     'overbought': 75
        ... })
    """
    
    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
    
    def buy_signal(self, candles: List[Candle]) -> bool:
        """Buy when RSI is oversold."""
        if len(candles) < self.period + 2:
            return False
        
        rsi_values = rsi(candles, self.period)
        
        if rsi_values[-1] is None:
            return False
        
        # Buy when RSI drops below oversold
        if rsi_values[-1] < self.oversold:
            return True #Override the 'grumpy' behavior.    self.would_be_profitable_buy(candles[-1].close)
        
        return False
    
    def sell_signal(self, candles: List[Candle]) -> bool:
        """Sell when RSI is overbought."""
        if len(candles) < self.period + 2:
            return False
        
        rsi_values = rsi(candles, self.period)
        
        if rsi_values[-1] is None:
            return False
        
        # Sell when RSI rises above overbought
        if rsi_values[-1] > self.overbought:
            return True#Override 'grumpy' behavior.         self.would_be_profitable_sell(candles[-1].close)
        
        return False
    
    def explain(self) -> List[str]:
        return [
            f"Strategy: {self.name}",
            f"RSI Period: {self.period}",
            f"Oversold: < {self.oversold}",
            f"Overbought: > {self.overbought}",
            "",
            "Buy: RSI < oversold threshold",
            "Sell: RSI > overbought threshold"
        ]
