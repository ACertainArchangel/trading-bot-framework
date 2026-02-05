"""
Bollinger Bands Strategy

Buys when price touches the lower band, sells when it touches the upper band.
"""

from typing import List
from ..base import Strategy
from ...core.candle import Candle
from ...indicators import bollinger_bands


class BollingerStrategy(Strategy):
    """
    Bollinger Bands Mean Reversion Strategy.
    
    Assumes price will revert to the mean. Buys when price touches
    the lower band and sells when it touches the upper band.
    
    Parameters:
        period: SMA period for middle band (default: 20)
        std_dev: Standard deviation multiplier (default: 2.0)
    
    Example:
        >>> from framework import backtest
        >>> from framework.strategies.examples import BollingerStrategy
        >>> 
        >>> result = backtest(BollingerStrategy, months=6, strategy_params={
        ...     'period': 20,
        ...     'std_dev': 2.5
        ... })
    """
    
    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.period = period
        self.std_dev = std_dev
    
    def buy_signal(self, candles: List[Candle]) -> bool:
        """Buy when price touches lower band."""
        if len(candles) < self.period + 1:
            return False
        
        bb = bollinger_bands(candles, self.period, self.std_dev)
        
        if bb['lower'][-1] is None:
            return False
        
        # Buy when price is at or below lower band
        if candles[-1].close <= bb['lower'][-1]:
            return True #Override the 'grumpy' behavior.    self.would_be_profitable_buy(candles[-1].close)
        
        return False
    
    def sell_signal(self, candles: List[Candle]) -> bool:
        """Sell when price touches upper band."""
        if len(candles) < self.period + 1:
            return False
        
        bb = bollinger_bands(candles, self.period, self.std_dev)
        
        if bb['upper'][-1] is None:
            return False
        
        # Sell when price is at or above upper band
        if candles[-1].close >= bb['upper'][-1]:
            return True#Override 'grumpy' behavior.         self.would_be_profitable_sell(candles[-1].close)
        
        return False
    
    def explain(self) -> List[str]:
        return [
            f"Strategy: {self.name}",
            f"Period: {self.period}",
            f"Std Dev: {self.std_dev}",
            "",
            "Buy: Price touches lower band",
            "Sell: Price touches upper band"
        ]
