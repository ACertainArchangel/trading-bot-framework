from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional, Callable
import threading
import time
from CBData import CoinbaseDataFetcher


class TickerStream:
    """
    Real-time streaming candlestick data with automatic updates.
    
    Initializes with historical data and maintains a background thread that
    fetches new candles as they complete, keeping your dataset always up-to-date.
    """
    
    def __init__(
        self, 
        start_date: datetime,
        product_id: str = "BTC-USD",
        granularity: str = '1m',
        on_new_candle: Optional[Callable[[Tuple], None]] = None,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the ticker stream.
        
        Args:
            start_date: Historical start point (will fetch all data from here to now)
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")
            granularity: Candle size ('1m', '5m', '15m', '1h', '6h', '1d')
            on_new_candle: Optional callback function called when new candle arrives
            logger: Optional function for output (defaults to print). Signature: logger(message: str)
        """
        self.product_id = product_id
        self.granularity = granularity
        self.on_new_candle = on_new_candle
        self.log = logger if logger else print
        
        # Thread safety
        self._lock = threading.Lock()
        self._candles: List[Tuple] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Fetcher
        self.fetcher = CoinbaseDataFetcher(product_id=product_id)
        self.granularity_seconds = self.fetcher.GRANULARITIES[granularity]
        
        self.log(f"🔄 Loading historical data from {start_date.isoformat()}...")
        initial_data = self.fetcher.fetch_candles(start_date, None, granularity)
        
        if not initial_data:
            raise RuntimeError(f"Failed to load initial data from {start_date.isoformat()}. Check date range or API status.")
        
        with self._lock:
            self._candles = initial_data
        
        self.log(f"✅ Loaded {len(initial_data)} historical candles")
        self.log(f"📊 Data range: {self._format_timestamp(initial_data[0][0])} to {self._format_timestamp(initial_data[-1][0])}")
    
    def start(self):
        """Start the background thread that fetches new candles."""
        if self._running:
            self.log("⚠️  Stream already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        self.log(f"🚀 Live stream started for {self.product_id} ({self.granularity})")
    
    def stop(self):
        """Stop the background thread."""
        if not self._running:
            return
        
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.log("🛑 Stream stopped")
    
    def get_candles(self, count: Optional[int] = None) -> List[Tuple]:
        """
        Get the candle data (thread-safe).
        
        Args:
            count: Number of most recent candles to return (None for all)
        
        Returns:
            List of candles: [[timestamp, low, high, open, close, volume], ...]
        """
        with self._lock:
            if count is None:
                return self._candles.copy()
            return self._candles[-count:].copy()
    
    def get_latest(self) -> Optional[Tuple]:
        """Get the most recent candle."""
        with self._lock:
            return self._candles[-1] if self._candles else None
    
    def __len__(self) -> int:
        """Return the number of candles in the stream."""
        with self._lock:
            return len(self._candles)
    
    def _update_loop(self):
        """Background thread that periodically checks for new candles."""
        while self._running:
            try:
                # Calculate when the next candle should be complete
                now = datetime.now(timezone.utc)
                last_candle = self.get_latest()
                
                if last_candle:
                    last_timestamp = datetime.fromtimestamp(last_candle[0], tz=timezone.utc)
                    next_candle_time = last_timestamp + timedelta(seconds=self.granularity_seconds)
                    
                    # Wait until the next candle should be complete (plus small buffer)
                    sleep_seconds = (next_candle_time - now).total_seconds() + 5
                    
                    if sleep_seconds > 0:
                        # Sleep in small intervals so we can stop quickly if needed
                        while sleep_seconds > 0 and self._running:
                            time.sleep(min(1, sleep_seconds))
                            sleep_seconds -= 1
                    
                    if not self._running:
                        break
                    
                    # Fetch new candles
                    new_candles = self.fetcher.fetch_candles(
                        last_timestamp + timedelta(seconds=self.granularity_seconds),
                        None,
                        self.granularity
                    )
                    
                    if new_candles:
                        with self._lock:
                            # Add only candles we don't already have
                            existing_timestamps = {c[0] for c in self._candles}
                            for candle in new_candles:
                                if candle[0] not in existing_timestamps:
                                    self._candles.append(candle)

                                    #We already log on the ticker stream feed so no need to double log here
                                    #self.log(f"📈 New candle: {self._format_candle(candle)}")
                                    
                                    # Call user callback if provided
                                    if self.on_new_candle:
                                        try:
                                            self.on_new_candle(candle)
                                        except Exception as e:
                                            self.log(f"⚠️  Error in callback: {e}")
                else:
                    # No candles yet, wait a bit
                    time.sleep(5)
                    
            except Exception as e:
                self.log(f"❌ Error in update loop: {e}")
                time.sleep(10)  # Wait before retrying
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format a Unix timestamp as a readable string."""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    def _format_candle(self, candle: Tuple) -> str:
        """Format a candle for display."""
        ts = self._format_timestamp(candle[0])
        return f"{ts} | O:{candle[3]:.2f} H:{candle[2]:.2f} L:{candle[1]:.2f} C:{candle[4]:.2f} V:{candle[5]:.4f}"
    
    def __enter__(self):
        """Context manager support."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.stop()


if __name__ == "__main__":
    # Example 1: Default behavior (prints to console)
    print("=" * 70)
    print("Example 1: Default logger (stdout)")
    print("=" * 70)
    
    start_date = datetime.now(timezone.utc) - timedelta(hours=1)
    stream = TickerStream(start_date, product_id="BTC-USD", granularity='1m')
    
    print(f"\n📊 Current data points: {len(stream)}")
    print(f"🕐 Latest candle: {stream._format_candle(stream.get_latest())}")
    stream.stop()
    
    # Example 2: Log to file
    print("\n" + "=" * 70)
    print("Example 2: Custom logger (file)")
    print("=" * 70)
    
    def file_logger(msg):
        with open("stream.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")
        print(f"[FILE] {msg}")  # Also show in console
    
    start_date = datetime.now(timezone.utc) - timedelta(minutes=30)
    stream2 = TickerStream(start_date, logger=file_logger)
    print("✅ Check 'stream.log' for output")
    stream2.stop()
    
    # Example 3: Silent mode (no output)
    print("\n" + "=" * 70)
    print("Example 3: Silent mode")
    print("=" * 70)
    
    silent_stream = TickerStream(
        datetime.now(timezone.utc) - timedelta(minutes=10),
        logger=lambda msg: None  # Completely silent
    )
    print(f"✅ Loaded {len(silent_stream)} candles silently")
    silent_stream.stop()
    
    # Example 4: Prefixed logger (useful for multiple streams)
    print("\n" + "=" * 70)
    print("Example 4: Multi-stream with prefixes")
    print("=" * 70)
    
    def make_logger(prefix):
        return lambda msg: print(f"[{prefix}] {msg}")
    
    btc_stream = TickerStream(
        datetime.now(timezone.utc) - timedelta(minutes=5),
        product_id="BTC-USD",
        logger=make_logger("BTC")
    )
    
    eth_stream = TickerStream(
        datetime.now(timezone.utc) - timedelta(minutes=5),
        product_id="ETH-USD",
        logger=make_logger("ETH")
    )
    
    print(f"✅ BTC: {len(btc_stream)} candles | ETH: {len(eth_stream)} candles")
    btc_stream.stop()
    eth_stream.stop()
    
    print("\n✅ All examples completed!")
