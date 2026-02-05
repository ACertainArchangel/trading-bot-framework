"""
Runners module - Easy functions to run strategies.

Provides simple functions for backtesting, paper trading, and live trading.
"""

from .backtest import backtest, BacktestResult, batch_backtest, visualize_backtest
from .paper import paper_trade
from .live import live_trade
from .simulate import simulate

__all__ = [
    'backtest',
    'BacktestResult',
    'batch_backtest',
    'visualize_backtest',
    'paper_trade',
    'live_trade',
    'simulate'
]
