#!/usr/bin/env python3
"""
Paper Trading Example

Run paper trading with a live dashboard.

Run with: python examples/paper_trading.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework import paper_trade
from framework.strategies.examples import EMACrossover


def main():
    print("📝 Paper Trading Example")
    print("=" * 50)
    print()
    print("This will start paper trading with a live web dashboard.")
    print("The dashboard shows real-time price, trades, and performance.")
    print()
    
    paper_trade(
        EMACrossover,
        starting_balance=1000,
        product_id="BTC-USD",
        granularity="5m",
        dashboard=True,
        dashboard_port=5002,
        strategy_params={'fast_period': 9, 'slow_period': 21}
    )


if __name__ == "__main__":
    main()
