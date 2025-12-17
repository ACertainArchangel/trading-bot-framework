"""
Coinbase Live Ticker Stream

Fetches real-time data from Coinbase Exchange API.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Tuple
import time
from .base import TickerStream
from CBData import CoinbaseDataFetcher


class CBTickerStream(TickerStream):
    """
    Live streaming candlestick data from Coinbase Exchange.
    
    Initializes with historical data and maintains a background thread that
    fetches new candles as they complete, keeping your dataset always up-to-date.
    """
    
    def __init__(
        self, 
        start_date: datetime,
        product_id: str = "BTC-USD",
        granularity: str = '1m',
        on_new_candle=None,
        logger=None
    ):
        """
        Initialize the Coinbase ticker stream.
        
        Args:
            start_date: Historical start point (will fetch all data from here to now)
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")
            granularity: Candle size ('1m', '5m', '15m', '1h', '6h', '1d')
            on_new_candle: Optional callback function called when new candle arrives
            logger: Optional function for output (defaults to print)
        """
        # Initialize parent
        super().__init__(product_id, granularity, on_new_candle, logger)
        
        # Coinbase-specific setup
        self.fetcher = CoinbaseDataFetcher(product_id=product_id)
        self.granularity_seconds = self.fetcher.GRANULARITIES[granularity]
        self.start_date = start_date
        
        # Load initial data
        initial_data = self._load_initial_data()
        
        with self._lock:
            self._candles = initial_data
        
        self.log(f"✅ Loaded {len(initial_data)} historical candles")
        if initial_data:
            self.log(f"📊 Data range: {self._format_timestamp(initial_data[0][0])} to {self._format_timestamp(initial_data[-1][0])}")
    
    def _load_initial_data(self) -> List[Tuple]:
        """Load historical data from Coinbase."""
        self.log(f"🔄 Loading historical data from {self.start_date.isoformat()}...")
        
        initial_data = self.fetcher.fetch_candles(self.start_date, None, self.granularity)
        
        if not initial_data:
            raise RuntimeError(f"Failed to load initial data from {self.start_date.isoformat()}. Check date range or API status.")
        
        return initial_data
    
    def _update_loop(self):
        """Background thread that periodically checks for new candles from Coinbase."""
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
                        # Add only candles we don't already have
                        existing_timestamps = {c[0] for c in self.get_candles()}
                        for candle in new_candles:
                            if candle[0] not in existing_timestamps:
                                self._notify_new_candle(candle)
                else:
                    # No candles yet, wait a bit
                    time.sleep(5)
                    
            except Exception as e:
                self.log(f"❌ Error in update loop: {e}")
                time.sleep(10)  # Wait before retrying
