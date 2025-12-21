"""
Base TickerStream Abstract Class

Defines the interface that all ticker streams must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Tuple, Optional, Callable
import threading


class TickerStream(ABC):
    """
    Abstract base class for ticker streams.
    
    All implementations must provide:
    - Historical data loading
    - Real-time or simulated updates
    - Thread-safe data access
    """
    
    def __init__(
        self,
        product_id: str = "BTC-USD",
        granularity: str = '1m',
        on_new_candle: Optional[Callable[[Tuple], None]] = None,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the ticker stream.
        
        Args:
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")
            granularity: Candle size ('1m', '5m', '15m', '1h', '6h', '1d')
            on_new_candle: Optional callback function called when new candle arrives
            logger: Optional function for output (defaults to print)
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
    
    @abstractmethod
    def _load_initial_data(self) -> List[Tuple]:
        """
        Load initial historical data.
        
        Returns:
            List of candles: [[timestamp, low, high, open, close, volume], ...]
        """
        pass
    
    @abstractmethod
    def _update_loop(self):
        """
        Background thread that handles new candle updates.
        Implementation varies by stream type (live vs replay).
        """
        pass
    
    def start(self):
        """Start the background thread that fetches/replays new candles."""
        if self._running:
            self.log("⚠️  Stream already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        self.log(f"🚀 Stream started for {self.product_id} ({self.granularity})")
    
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
    
    def __enter__(self):
        """Context manager support."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.stop()
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format a Unix timestamp as a readable string."""
        dt = datetime.fromtimestamp(timestamp, tz=datetime.now().astimezone().tzinfo)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def _format_candle(self, candle: Tuple) -> str:
        """Format a candle for display."""
        ts = self._format_timestamp(candle[0])
        return f"{ts} | O:{candle[3]:.2f} H:{candle[2]:.2f} L:{candle[1]:.2f} C:{candle[4]:.2f} V:{candle[5]:.4f}"
    
    def _notify_new_candle(self, candle: Tuple):
        """
        Add a new candle and notify callback.
        Should be called by subclasses when new data arrives.
        """
        with self._lock:
            self._candles.append(candle)
        
        self.log(f"📈 New candle: {self._format_candle(candle)}")
        
        # Call user callback if provided
        if self.on_new_candle:
            try:
                self.on_new_candle(candle)
            except Exception as e:
                self.log(f"⚠️  Error in callback: {e}")
