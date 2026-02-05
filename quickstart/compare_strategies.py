#!/usr/bin/env python3
"""
Compare Strategies Example

Compare multiple strategies side by side using batch_backtest.

Run with: python examples/compare_strategies.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework import batch_backtest
from framework.strategies.examples import (
    EMACrossover,
    MACrossover,
    RSIStrategy,
    MACDStrategy,
    BollingerStrategy
)


def main():
    print("📊 Strategy Comparison")
    print("=" * 60)
    
    # Define strategies to compare
    strategies = [
        {"strategy": EMACrossover, "params": {"fast_period": 9, "slow_period": 21}},
        {"strategy": EMACrossover, "params": {"fast_period": 12, "slow_period": 26}},
        {"strategy": MACrossover, "params": {"fast_period": 10, "slow_period": 30}},
        {"strategy": RSIStrategy, "params": {"oversold": 30, "overbought": 70}},
        {"strategy": RSIStrategy, "params": {"oversold": 25, "overbought": 75}},
        {"strategy": MACDStrategy, "params": {"allocation": {"long": 1000, "short": -1000}}}, # Totally bug it out to see what happens. As you may be able to tell, this thing doesn't know what a margin call is. A casual -2294112700155402125312.00%. Still bullish.
        {"strategy": BollingerStrategy, "params": {"std_dev": 2.0}},
    ]
    
    # Run all backtests
    results = batch_backtest(
        strategies,
        months=3,
        starting_balance=1000,
        fee_rate=0.00025 # Coinbase VIP 4 fee
    )
    
    # Sort by return
    successful = sorted(
        [r for r in results if r.success],
        key=lambda r: r.total_return_pct,
        reverse=True
    )
    
    # Print leaderboard
    print()
    print("🏆 STRATEGY LEADERBOARD")
    print("-" * 60)
    print(f"{'Rank':<5} {'Strategy':<25} {'Return':>10} {'Trades':>8} {'Win%':>8}")
    print("-" * 60)
    
    medals = ["🥇", "🥈", "🥉"]
    for i, result in enumerate(successful):
        medal = medals[i] if i < 3 else "  "
        print(f"{medal}{i+1:<3} {result.strategy_name:<25} {result.total_return_pct:>+9.2f}% {result.total_trades:>8} {result.win_rate_pct:>7.1f}%")
    
    print()
    
    # Best strategy details
    if successful:
        best = successful[0]
        print(f"🏆 Winner: {best.strategy_name}")
        print(f"   Params: {best.strategy_params}")
        print(f"   Return: {best.total_return_pct:+.2f}%")
        print(f"   APY: {best.annualized_return_pct:+.2f}%")


if __name__ == "__main__":
    main()
