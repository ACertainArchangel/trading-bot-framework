#!/usr/bin/env python3
"""
Custom Strategy Example

Shows how to create your own trading strategy and backtest.

Run with: python examples/custom_strategy.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework import Strategy, Candle, backtest
from framework.indicators import ema, rsi


class MyMomentumStrategy(Strategy):
    """
    A custom momentum strategy using EMA crossovers with RSI confirmation.
    
    Buy when:
    - Fast EMA crosses above slow EMA (bullish momentum)
    - RSI < 70 (not overbought)
    
    Sell when:
    - Fast EMA crosses below slow EMA (bearish momentum)
    - RSI > 30 (not oversold)
    """
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21, **kwargs):
        super().__init__(**kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def buy_signal(self, candles: list[Candle]) -> bool:
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        rsi_vals = rsi(candles, 14)
        
        if None in [fast[-1], fast[-2], slow[-1], slow[-2], rsi_vals[-1]]:
            return False
        
        # Bullish crossover + RSI not overbought
        crossed_above = fast[-1] > slow[-1] and fast[-2] <= slow[-2]
        rsi_ok = rsi_vals[-1] < 70
        
        return crossed_above and rsi_ok
    
    def sell_signal(self, candles: list[Candle]) -> bool:
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        rsi_vals = rsi(candles, 14)
        
        if None in [fast[-1], fast[-2], slow[-1], slow[-2], rsi_vals[-1]]:
            return False
        
        # Bearish crossover + RSI not oversold
        crossed_below = fast[-1] < slow[-1] and fast[-2] >= slow[-2]
        rsi_ok = rsi_vals[-1] > 30
        
        return crossed_below and rsi_ok


def main():
    print("🎯 Custom Strategy Example")
    print("=" * 50)
    
    result = backtest(
        MyMomentumStrategy,
        months=3,
        starting_balance=1000,
        strategy_params={'fast_period': 9, 'slow_period': 21}
    )
    
    print(result)


if __name__ == "__main__":
    main()
