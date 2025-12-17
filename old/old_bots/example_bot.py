"""
Example: Using Different Stream Types with the Same Bot Logic

Demonstrates how any bot can work with any stream type.
"""

from datetime import datetime, timezone, timedelta
from streams import CBTickerStream, TestTickerStream
import time


class SimpleMovingAverageBot:
    """
    Example trading bot that works with ANY stream type.
    
    Strategy: Buy when price > 20-period SMA, Sell when price < SMA
    """
    
    def __init__(self, stream, sma_period=20):
        self.stream = stream
        self.sma_period = sma_period
        self.position = None  # 'long', 'short', or None
        self.trades = []
        
    def on_candle(self, candle):
        """Called whenever a new candle arrives."""
        # Get recent candles for analysis
        recent = self.stream.get_candles(count=self.sma_period)
        
        if len(recent) < self.sma_period:
            return  # Not enough data yet
        
        # Calculate SMA
        prices = [c[4] for c in recent]  # close prices
        sma = sum(prices) / len(prices)
        
        current_price = candle[4]
        timestamp = datetime.fromtimestamp(candle[0], tz=timezone.utc)
        
        # Trading logic
        if current_price > sma and self.position != 'long':
            print(f"🟢 BUY  @ ${current_price:.2f} (SMA: ${sma:.2f}) - {timestamp}")
            self.position = 'long'
            self.trades.append({'type': 'BUY', 'price': current_price, 'time': timestamp})
            
        elif current_price < sma and self.position != 'short':
            print(f"🔴 SELL @ ${current_price:.2f} (SMA: ${sma:.2f}) - {timestamp}")
            self.position = 'short'
            self.trades.append({'type': 'SELL', 'price': current_price, 'time': timestamp})
    
    def report(self):
        """Print trading summary."""
        print("\n" + "=" * 70)
        print("Trading Summary")
        print("=" * 70)
        print(f"Total trades: {len(self.trades)}")
        print(f"Final position: {self.position or 'None'}")
        
        if self.trades:
            print("\nTrade history:")
            for trade in self.trades[-5:]:  # Last 5 trades
                print(f"  {trade['type']:4} @ ${trade['price']:8.2f} - {trade['time']}")


def test_with_live_stream():
    """Example 1: Use bot with LIVE Coinbase stream."""
    print("=" * 70)
    print("Example 1: Bot with LIVE Coinbase Stream")
    print("=" * 70)
    
    # Create live stream
    start_date = datetime.now(timezone.utc) - timedelta(hours=1)
    stream = CBTickerStream(
        start_date,
        product_id="BTC-USD",
        granularity='1m'
    )
    
    # Create bot
    bot = SimpleMovingAverageBot(stream, sma_period=20)
    
    # Connect bot to stream
    stream.on_new_candle = bot.on_candle
    stream.start()
    
    print("\n⏳ Running bot for 30 seconds with live data...\n")
    time.sleep(30)
    
    stream.stop()
    bot.report()


def test_with_backtest_stream():
    """Example 2: Use SAME bot with TEST stream (backtesting)."""
    print("\n" + "=" * 70)
    print("Example 2: SAME Bot with TEST Stream (Backtesting)")
    print("=" * 70)
    
    # Create test stream (replay historical data fast)
    start = datetime(2025, 12, 15, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 12, 15, 6, 0, 0, tzinfo=timezone.utc)
    
    stream = TestTickerStream(
        start_date=start,
        end_date=end,
        product_id="BTC-USD",
        granularity='1m',
        playback_speed=0.01,  # 100 candles per second for fast backtesting
        initial_window=50
    )
    
    # Create bot (SAME CODE as above!)
    bot = SimpleMovingAverageBot(stream, sma_period=20)
    
    # Connect bot to stream
    stream.on_new_candle = bot.on_candle
    stream.start()
    
    print("\n⚡ Running backtest at 100x speed...\n")
    
    # Wait for backtest to complete
    while not stream.is_complete() and stream._running:
        time.sleep(1)
        progress = stream.get_progress()
        print(f"  Progress: {progress['percent']:.1f}% ({progress['current']}/{progress['total']})", end='\r')
    
    print("\n")
    stream.stop()
    bot.report()


if __name__ == "__main__":
    import sys
    
    print("\n🤖 Stream-Agnostic Trading Bot Demo\n")
    print("This demonstrates that the SAME bot code works with:")
    print("  1. Live Coinbase stream (real-time data)")
    print("  2. Test stream (historical replay for backtesting)")
    print("\nChoose mode:")
    print("  1 = Live stream (30 seconds)")
    print("  2 = Backtest (6 hours in ~4 seconds)")
    print("  3 = Both")
    
    choice = input("\nYour choice (1/2/3): ").strip()
    
    if choice == '1':
        test_with_live_stream()
    elif choice == '2':
        test_with_backtest_stream()
    elif choice == '3':
        test_with_live_stream()
        test_with_backtest_stream()
    else:
        print("Invalid choice. Running backtest by default.")
        test_with_backtest_stream()
    
    print("\n✅ Demo complete!")
