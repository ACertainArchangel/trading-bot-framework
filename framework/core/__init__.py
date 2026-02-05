"""
Core components of the trading framework.

This module contains the fundamental data structures and types used throughout
the framework: candles, signals, orders, and positions.
"""

from .candle import Candle
from .signals import Signal, EntrySignal, SignalStrength

__all__ = [
    'Candle',
    'Signal',
    'EntrySignal',
    'SignalStrength',
]
