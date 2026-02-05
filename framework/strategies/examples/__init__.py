"""
Example Strategies - Ready-to-use strategy implementations.

These demonstrate common patterns and can be used as starting points.
"""

from .ma_crossover import MACrossover
from .rsi_strategy import RSIStrategy
from .macd_strategy import MACDStrategy
from .bollinger_strategy import BollingerStrategy
from .ema_crossover import EMACrossover

__all__ = [
    'MACrossover',
    'RSIStrategy', 
    'MACDStrategy',
    'BollingerStrategy',
    'EMACrossover',
]
