#!/usr/bin/env python3
"""
Quick launcher for web dashboard with different configurations.
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone

def launch_live_btc():
    """Launch with live BTC-USD stream."""
    print("🚀 Launching: Live BTC-USD (1-minute candles)")
    subprocess.run([
        sys.executable, "web_dashboard.py",
        "--stream", "live",
        "--product", "BTC-USD",
        "--granularity", "1m",
        "--port", "5001"
    ])

def launch_live_eth():
    """Launch with live ETH-USD stream."""
    print("🚀 Launching: Live ETH-USD (1-minute candles)")
    subprocess.run([
        sys.executable, "web_dashboard.py",
        "--stream", "live",
        "--product", "ETH-USD",
        "--granularity", "1m",
        "--port", "5001"
    ])

def launch_backtest_fast():
    """Launch with fast historical replay (2 days ago)."""
    # Use data from 2 days ago, 4 hours (240 candles - under 300 limit)
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    start = two_days_ago.replace(hour=12, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=4)
    
    print(f"⚡ Launching: Fast Backtest ({start.strftime('%Y-%m-%d %H:%M')} UTC, 4 hours, 0.1s per candle)")
    subprocess.run([
        sys.executable, "web_dashboard.py",
        "--stream", "test",
        "--product", "BTC-USD",
        "--granularity", "1m",
        "--start-date", start.isoformat(),
        "--end-date", end.isoformat(),
        "--speed", "0.1",
        "--port", "5001"
    ])

def launch_backtest_realtime():
    """Launch with real-time historical replay (2 days ago, 2 hours)."""
    # Use data from 2 days ago, 2 hours (120 candles - well under limit)
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    start = two_days_ago.replace(hour=12, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=2)
    
    print(f"🎬 Launching: Real-time Backtest ({start.strftime('%Y-%m-%d %H:%M')} UTC, 2 hours, 1s per candle)")
    subprocess.run([
        sys.executable, "web_dashboard.py",
        "--stream", "test",
        "--product", "BTC-USD",
        "--granularity", "1m",
        "--start-date", start.isoformat(),
        "--end-date", end.isoformat(),
        "--speed", "1.0",
        "--port", "5001"
    ])

def launch_backtest_specific():
    """Launch with specific date range."""
    print("📅 Launching: Custom Backtest")
    print("Testing: Dec 13, 2025, 12:00-16:00 UTC (4 hours)")
    subprocess.run([
        sys.executable, "web_dashboard.py",
        "--stream", "test",
        "--product", "BTC-USD",
        "--granularity", "1m",
        "--start-date", "2025-12-13T12:00:00",
        "--end-date", "2025-12-13T16:00:00",
        "--speed", "0.05",  # 20 candles per second
        "--port", "5001"
    ])


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🎛️  Trading Dashboard Launcher")
    print("=" * 70)
    print("\nAvailable configurations:\n")
    print("  1. Live BTC-USD stream")
    print("  2. Live ETH-USD stream")
    print("  3. Fast backtest (2 days ago, 4 hours, 10x speed)")
    print("  4. Real-time backtest (2 days ago, 2 hours, 1x speed)")
    print("  5. Custom backtest (Dec 13, 4 hours, 20x speed)")
    print()
    
    choice = input("Choose configuration (1-5): ").strip()
    
    configs = {
        '1': launch_live_btc,
        '2': launch_live_eth,
        '3': launch_backtest_fast,
        '4': launch_backtest_realtime,
        '5': launch_backtest_specific
    }
    
    if choice in configs:
        print()
        configs[choice]()
    else:
        print("\n❌ Invalid choice")
        sys.exit(1)
