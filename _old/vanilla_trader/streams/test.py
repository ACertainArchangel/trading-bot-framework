"""
Test Ticker Stream for Backtesting

Replays historical data at a fixed rate for strategy testing.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Tuple
import time
from .base import TickerStream
from CBData import CoinbaseDataFetcher


class TestTickerStream(TickerStream):
    """
    Historical data replay stream for backtesting trading strategies.
    
    Loads a window of historical data and replays it at a specified rate
    (default: 1 candle per second), allowing you to test strategies against
    real market data in accelerated time.
    """
    
    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        product_id: str = "BTC-USD",
        granularity: str = '1m',
        playback_speed: float = 1.0,
        initial_window: int = 50,
        rate_limit_delay: float = 3.0,
        on_new_candle=None,
        logger=None
    ):
        """
        Initialize the test ticker stream.
        
        Args:
            start_date: Start of historical data period
            end_date: End of historical data period
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")
            granularity: Candle size ('1m', '5m', '15m', '1h', '6h', '1d')
            playback_speed: Playback rate in seconds per candle (default: 1.0 = 1 candle/sec)
            initial_window: Number of candles to start with (rest are fed progressively)
            rate_limit_delay: Delay in seconds between API chunk requests (default: 3.0)
            on_new_candle: Optional callback function called when new candle arrives
            logger: Optional function for output (defaults to print)
        """
        # Initialize parent
        super().__init__(product_id, granularity, on_new_candle, logger)
        
        # Handle both datetime objects and ISO strings
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        self.start_date = start_date
        self.end_date = end_date
        self.playback_speed = playback_speed
        self.initial_window = initial_window
        
        # Fetch all historical data with chunked loading
        self.log(f"🔄 Loading historical data from {start_date.isoformat()} to {end_date.isoformat()}...")
        fetcher = CoinbaseDataFetcher(product_id=product_id, rate_limit_delay=rate_limit_delay)
        self._all_data = fetcher.fetch_candles(start_date, end_date, granularity)
        
        if not self._all_data:
            raise RuntimeError(f"Failed to load historical data. Check date range or API status.")
        
        self.log(f"✅ Loaded {len(self._all_data)} total candles for backtesting")
        
        # Initialize with first N candles
        initial_data = self._load_initial_data()
        
        with self._lock:
            self._candles = initial_data
        
        # Track position in replay
        self._replay_index = len(initial_data)
        
        self.log(f"📊 Starting with {len(initial_data)} candles")
        self.log(f"⚡ Playback speed: {playback_speed}s per candle")
        self.log(f"📈 {len(self._all_data) - self._replay_index} candles remaining to replay")
    
    def _load_initial_data(self) -> List[Tuple]:
        """Load the initial window of candles."""
        return self._all_data[:self.initial_window]
    
    def _update_loop(self):
        """Background thread that replays historical candles at specified rate."""
        self.log("🎬 Starting playback...")
        
        while self._running and self._replay_index < len(self._all_data):
            try:
                # Get next candle
                candle = self._all_data[self._replay_index]
                self._replay_index += 1
                
                # Add to stream
                self._notify_new_candle(candle)
                
                # Wait for next candle based on playback speed
                time.sleep(self.playback_speed)
                
            except Exception as e:
                self.log(f"❌ Error in playback loop: {e}")
                break
        
        if self._replay_index >= len(self._all_data):
            self.log("🏁 Playback complete - all historical data replayed")
            self._running = False
    
    def get_progress(self) -> dict:
        """
        Get current playback progress.
        
        Returns:
            dict with keys: current, total, percent, remaining
        """
        total = len(self._all_data)
        current = self._replay_index
        return {
            'current': current,
            'total': total,
            'percent': (current / total * 100) if total > 0 else 0,
            'remaining': total - current
        }
    
    def is_complete(self) -> bool:
        """Check if all historical data has been replayed."""
        return self._replay_index >= len(self._all_data)


if __name__ == "__main__":
    # Example: Backtest on one day of data
    print("=" * 70)
    print("TestTickerStream Example - Backtesting")
    print("=" * 70)
    
    start = datetime(2025, 12, 15, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 12, 15, 6, 0, 0, tzinfo=timezone.utc)
    
    def on_candle(candle):
        """Example strategy callback."""
        price = candle[4]  # close price
        print(f"  Strategy received candle: ${price:.2f}")
    
    # Create test stream with fast playback
    stream = TestTickerStream(
        start_date=start,
        end_date=end,
        product_id="BTC-USD",
        granularity='1m',
        playback_speed=0.1,  # 10 candles per second for fast testing
        initial_window=50,
        on_new_candle=on_candle
    )
    
    stream.start()
    
    # Monitor progress
    while not stream.is_complete() and stream._running:
        time.sleep(2)
        progress = stream.get_progress()
        print(f"Progress: {progress['current']}/{progress['total']} ({progress['percent']:.1f}%)")
    
    stream.stop()
    print(f"\n✅ Backtest complete! Final candle count: {len(stream)}")
