#!/usr/bin/env python3
"""
Dynamic Allocation Example

Shows how to return allocation values directly from buy/sell signals.

Run with: python examples/dynamic_allocation.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework import Strategy, Candle, simulate
from framework.indicators import ema, rsi, atr


class AdaptiveStrategy(Strategy):
    """
    A strategy that adjusts position size based on market conditions.
    
    Instead of just returning True/False, buy_signal() and sell_signal()
    can return a float to specify the allocation for that trade:
    
    - buy_signal() returning 1.5 = buy with 150% position
    - sell_signal() returning -1.0 = sell and go short with 100% position
    """
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21, **kwargs):
        super().__init__(**kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def _get_rsi_allocation(self, candles: list[Candle]) -> float:
        """Calculate position size based on RSI."""
        if len(candles) < 14:
            return 1.0
        
        rsi_vals = rsi(candles, 14)
        if rsi_vals[-1] is None:
            return 1.0
        
        # Scale position based on RSI
        if rsi_vals[-1] > 70:
            return 0.5  # Half position when overbought
        elif rsi_vals[-1] < 30:
            return 1.5  # Larger position when oversold
        return 1.0
    
    def _is_high_volatility(self, candles: list[Candle]) -> bool:
        """Check if we're in a high volatility environment."""
        if len(candles) < 50:
            return False
        
        atr_vals = atr(candles, 14)
        if atr_vals[-1] is None:
            return False
        
        recent_atr = [v for v in atr_vals[-50:] if v is not None]
        if not recent_atr:
            return False
        
        avg_atr = sum(recent_atr) / len(recent_atr)
        return atr_vals[-1] > avg_atr * 1.5
    
    def buy_signal(self, candles: list[Candle]):
        """
        Return allocation multiplier instead of just True/False.
        
        - Return 0 or False = no signal
        - Return float > 0 = buy with that allocation
        """
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        
        if None in [fast[-1], fast[-2], slow[-1], slow[-2]]:
            return False
        
        # Check for bullish crossover
        if fast[-1] > slow[-1] and fast[-2] <= slow[-2]:
            # Return position size based on RSI
            return self._get_rsi_allocation(candles)
        
        return False
    
    def sell_signal(self, candles: list[Candle]):
        """
        Return allocation for short position.
        
        - Return 0 or False = no signal
        - Return True = just sell (no short)
        - Return float < 0 = sell and go short with that allocation
        """
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        
        if None in [fast[-1], fast[-2], slow[-1], slow[-2]]:
            return False
        
        # Check for bearish crossover
        if fast[-1] < slow[-1] and fast[-2] >= slow[-2]:
            # Only go short during high volatility
            if self._is_high_volatility(candles):
                return -1.0  # Go short
            return True  # Just exit, no short
        
        return False


def main():
    print("📈 Dynamic Allocation Example")
    print("=" * 50)
    print()
    print("This strategy returns allocation WITH the signal:")
    print("  - buy_signal() can return 0.5, 1.0, 1.5, etc.")
    print("  - sell_signal() can return True (exit) or -1.0 (short)")
    print()
    
    simulate(
        AdaptiveStrategy,
        days=14,
        starting_balance=1000,
        playback_speed=0.05,
        dashboard=True,
        strategy_params={'fast_period': 9, 'slow_period': 21}
    )


if __name__ == "__main__":
    main()
