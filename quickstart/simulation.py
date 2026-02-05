#!/usr/bin/env python3
"""
Simulation Example

Replay a backtest with a visual dashboard - watch trades unfold in real-time.

Run with: python examples/simulation.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework import simulate
from framework.strategies.examples import EMACrossover


def main():
    print("🎬 Simulation Example")
    print("=" * 50)
    print()
    print("This replays historical data with a live dashboard.")
    print("Watch as trades execute at adjustable playback speed.")
    print()
    
    simulate(
        EMACrossover,
        days=14,                    # 2 weeks of data
        starting_balance=1000,
        playback_speed=0.05,        # Fast: 20 candles/sec
        allocation={'short': -1, 'long': 1},  # Enable shorting
        dashboard=True,
        dashboard_port=5002,
        strategy_params={'fast_period': 9, 'slow_period': 21}
    )


if __name__ == "__main__":
    main()
