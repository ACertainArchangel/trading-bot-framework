"""
Trading interfaces - Abstract and concrete implementations.

Interfaces handle the actual execution of trades, whether simulated (paper)
or real (live). The bot uses the interface to execute trades.
"""

from .base import TradingInterface, Allocation, DEFAULT_ALLOCATION
from .paper import PaperInterface
from .coinbase import CoinbaseInterface

__all__ = [
    'TradingInterface',
    'PaperInterface',
    'CoinbaseInterface',
    'Allocation',
    'DEFAULT_ALLOCATION'
]
