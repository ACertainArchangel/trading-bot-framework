"""
Trading Framework - Rapid Prototyping, Testing & Deployment of Algorithmic Trading Strategies

A comprehensive framework for building, backtesting, paper trading, and deploying
trading strategies based on candlestick analysis.

Quick Start:
    from framework import Strategy, Candle, backtest, paper_trade, live_trade

    class MyStrategy(Strategy):
        def buy_signal(self, candles: list[Candle]) -> bool:
            # Your buy logic here
            return False
        
        def sell_signal(self, candles: list[Candle]) -> bool:
            # Your sell logic here
            return False

    # Backtest your strategy
    results = backtest(MyStrategy, months=3)
    
    # Paper trade with fake money
    paper_trade(MyStrategy, starting_balance=1000)
    
    # Go live!
    live_trade(MyStrategy, api_key="...", api_secret="...")

Author: Trading Framework
License: MIT
"""

__version__ = "2.0.0"

# Core types
from .core.candle import Candle
from .core.signals import Signal, EntrySignal, SignalStrength

# Strategy base class - THE main thing users implement
from .strategies.base import Strategy

# Running strategies
from .runners.backtest import backtest, BacktestResult, batch_backtest, visualize_backtest
from .runners.paper import paper_trade
from .runners.live import live_trade
from .runners.simulate import simulate

# Data fetching
from .data.fetcher import DataFetcher

# Visualization
from .dashboard import launch_dashboard

# Interfaces and allocation
from .interfaces.base import Allocation, DEFAULT_ALLOCATION

# Convenience exports
__all__ = [
    # Core types
    'Candle',
    'Signal',
    'EntrySignal', 
    'SignalStrength',
    
    # Strategy
    'Strategy',
    
    # Runners
    'backtest',
    'BacktestResult',
    'batch_backtest',
    'visualize_backtest',
    'paper_trade',
    'live_trade',
    'simulate',
    
    # Data
    'DataFetcher',
    
    # Visualization
    'launch_dashboard',
    
    # Allocation
    'Allocation',
    'DEFAULT_ALLOCATION',
]
