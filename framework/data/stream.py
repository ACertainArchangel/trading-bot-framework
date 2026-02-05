"""
Real-time data streaming for live trading.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional, Callable
import threading
import time

from ..core.candle import Candle
from .fetcher import DataFetcher


class BaseStream(ABC):
    """
    Abstract base class for data streams.
    
    Provides thread-safe candle storage and update callbacks.
    """
    
    def __init__(
        self,
        product_id: str = "BTC-USD",
        granularity: str = '1m',
        on_candle: Optional[Callable[[Candle], None]] = None,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the stream.
        
        Args:
            product_id: Trading pair (e.g., "BTC-USD")
            granularity: Candle size ('1m', '5m', '15m', '1h')
            on_candle: Callback when new candle arrives
            logger: Custom logging function
        """
        self.product_id = product_id
        self.granularity = granularity
        self.on_candle = on_candle
        self._log = logger or print
        
        self._lock = threading.Lock()
        self._candles: List[Candle] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    @abstractmethod
    def _load_initial(self) -> List[Candle]:
        """Load initial historical data. Override in subclasses."""
        pass
    
    @abstractmethod
    def _update_loop(self):
        """Background update loop. Override in subclasses."""
        pass
    
    def start(self):
        """Start the stream."""
        if self._running:
            self._log("⚠️  Stream already running")
            return
        
        # Load initial data
        self._log(f"📦 Loading initial data for {self.product_id}...")
        initial = self._load_initial()
        with self._lock:
            self._candles = initial
        self._log(f"✅ Loaded {len(initial)} candles")
        
        # Start background thread
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        self._log(f"🚀 Stream started ({self.granularity})")
    
    def stop(self):
        """Stop the stream."""
        if not self._running:
            return
        
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._log("🛑 Stream stopped")
    
    def get_candles(self, count: Optional[int] = None) -> List[Candle]:
        """
        Get candle data (thread-safe).
        
        Args:
            count: Number of recent candles (None = all)
        
        Returns:
            List of Candle objects
        """
        with self._lock:
            if count is None:
                return self._candles.copy()
            return self._candles[-count:].copy()
    
    def get_latest(self) -> Optional[Candle]:
        """Get the most recent candle."""
        with self._lock:
            return self._candles[-1] if self._candles else None
    
    def _add_candle(self, candle: Candle):
        """Add a new candle (internal use)."""
        with self._lock:
            self._candles.append(candle)
        
        self._log(f"📈 {candle}")
        
        if self.on_candle:
            try:
                self.on_candle(candle)
            except Exception as e:
                self._log(f"⚠️  Callback error: {e}")
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._candles)
    
    def is_data_valid(self) -> bool:
        """
        Check if stream data is valid. Override in subclasses for specific checks.
        Default implementation always returns True.
        """
        return True
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()


class LiveStream(BaseStream):
    """
    Real-time data stream from Coinbase.
    
    Polls the API at each candle close to get new data.
    Includes automatic gap detection and filling to ensure data integrity.
    
    Data Integrity:
        The stream continuously monitors for:
        - Missing candles (gaps) between consecutive timestamps
        - Stale data (latest candle too old)
        
        Use is_data_valid() to check if the data is complete and current.
        The paper_trade() and live_trade() functions automatically gate
        trades behind this check.
    
    Example:
        stream = LiveStream('BTC-USD', '1m')
        stream.start()
        
        while True:
            # Check data validity before making decisions
            if stream.is_data_valid():
                candles = stream.get_candles(100)
                # ... safe to use candles ...
            else:
                # Data has gaps or is stale - wait
                pass
            time.sleep(1)
    """
    
    GRANULARITY_SECONDS = {
        '1m': 60, '5m': 300, '15m': 900,
        '1h': 3600, '6h': 21600, '1d': 86400
    }
    
    def __init__(
        self,
        product_id: str = "BTC-USD",
        granularity: str = '1m',
        history_hours: int = 24,
        on_candle: Optional[Callable[[Candle], None]] = None,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize live stream.
        
        Args:
            product_id: Trading pair
            granularity: Candle size
            history_hours: Hours of history to load initially
            on_candle: Callback for new candles
            logger: Custom logger
        """
        super().__init__(product_id, granularity, on_candle, logger)
        self.history_hours = history_hours
        self._fetcher = DataFetcher(product_id, verbose=False)
    
    def _load_initial(self) -> List[Candle]:
        """Load initial historical data with retry logic."""
        hours = self.history_hours
        days = max(1, hours // 24 + 1)
        
        while True:
            candles = self._fetcher.get_candles(
                days=days,
                granularity=self.granularity,
                as_objects=True
            )
            if candles:
                return candles
            
            self._log(f"⚠️  Initial load failed. Retrying in 5s...")
            time.sleep(5)
    
    def _has_gaps(self) -> bool:
        """Check if there are any gaps in the candle data."""
        with self._lock:
            if len(self._candles) < 2:
                return False
            
            interval = self.GRANULARITY_SECONDS.get(self.granularity, 60)
            
            for i in range(1, len(self._candles)):
                expected_ts = self._candles[i-1].timestamp + interval
                actual_ts = self._candles[i].timestamp
                
                # Allow small tolerance for timing differences
                if actual_ts - expected_ts > interval + 5:
                    return True
        
        return False
    
    def _is_stale(self) -> bool:
        """Check if the latest candle is too old (we're missing recent data)."""
        with self._lock:
            if not self._candles:
                return True
            
            latest_ts = self._candles[-1].timestamp
            interval = self.GRANULARITY_SECONDS.get(self.granularity, 60)
            now = time.time()
            
            # Data is stale if we're more than 2 intervals behind
            return (now - latest_ts) > (interval * 2 + 10)
    
    def is_data_valid(self) -> bool:
        """
        Check if the stream data is complete and up-to-date.
        Returns True only if:
        - No gaps exist between candles
        - Latest candle is recent (not stale)
        """
        return not self._has_gaps() and not self._is_stale()
    
    def _fill_gaps(self):
        """Attempt to fill any gaps in the candle data."""
        with self._lock:
            if len(self._candles) < 2:
                return
            
            interval = self.GRANULARITY_SECONDS.get(self.granularity, 60)
            gaps = []
            
            for i in range(1, len(self._candles)):
                expected_ts = self._candles[i-1].timestamp + interval
                actual_ts = self._candles[i].timestamp
                
                if actual_ts - expected_ts > interval + 5:
                    gaps.append((expected_ts, actual_ts))
        
        if not gaps:
            return
        
        self._log(f"⚠️  Found {len(gaps)} gap(s), filling...")
        
        for gap_start, gap_end in gaps:
            start_dt = datetime.fromtimestamp(gap_start, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(gap_end, tz=timezone.utc)
            
            try:
                missing = self._fetcher.get_candles(
                    start=start_dt,
                    end=end_dt,
                    granularity=self.granularity,
                    as_objects=True
                )
                
                if missing:
                    with self._lock:
                        self._candles.extend(missing)
                        self._candles.sort(key=lambda c: c.timestamp)
                        # Remove duplicates
                        seen = set()
                        unique = []
                        for c in self._candles:
                            if c.timestamp not in seen:
                                seen.add(c.timestamp)
                                unique.append(c)
                        self._candles = unique
                    self._log(f"✅ Filled gap with {len(missing)} candles")
            except Exception as e:
                self._log(f"⚠️  Error filling gap: {e}")
    
    def _update_loop(self):
        """Poll for new candles, continuously trying to keep data complete."""
        interval = self.GRANULARITY_SECONDS.get(self.granularity, 60)
        
        while self._running:
            try:
                # Always try to get latest candles
                latest = self._fetcher.get_latest(count=10, granularity=self.granularity)
                
                if latest and len(latest) > 0:
                    with self._lock:
                        existing_ts = {c.timestamp for c in self._candles}
                    
                    for new_candle in latest:
                        if new_candle.timestamp not in existing_ts:
                            self._add_candle(new_candle)
                            existing_ts.add(new_candle.timestamp)
                    
                    # Check and fill any gaps
                    self._fill_gaps()
                else:
                    self._log(f"⚠️  Failed to fetch candles, retrying...")
                
            except Exception as e:
                self._log(f"⚠️  Update error: {e}")
            
            # Wait before next poll
            time.sleep(interval)


class ReplayStream(BaseStream):
    """
    Replay historical data as if it were live.
    
    Useful for backtesting with the same streaming interface.
    
    Example:
        candles = fetcher.get_candles(months=3)
        stream = ReplayStream(candles, speed=100)  # 100x speed
        stream.start()
    """
    
    def __init__(
        self,
        candles: List[Candle],
        speed: float = 1.0,
        on_candle: Optional[Callable[[Candle], None]] = None,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize replay stream.
        
        Args:
            candles: Historical candles to replay
            speed: Replay speed multiplier (1.0 = real-time)
            on_candle: Callback for each candle
            logger: Custom logger
        """
        super().__init__(logger=logger)
        self._all_candles = candles
        self.speed = speed
        self.on_candle = on_candle
        self._replay_index = 0
    
    def _load_initial(self) -> List[Candle]:
        """Return first portion of candles."""
        # Start with first 20% of data
        initial_count = max(50, len(self._all_candles) // 5)
        self._replay_index = initial_count
        return self._all_candles[:initial_count]
    
    def _update_loop(self):
        """Replay remaining candles."""
        if len(self._all_candles) < 2:
            return
        
        # Calculate delay between candles
        first = self._all_candles[0].timestamp
        second = self._all_candles[1].timestamp
        interval = (second - first) / self.speed
        
        while self._running and self._replay_index < len(self._all_candles):
            candle = self._all_candles[self._replay_index]
            self._add_candle(candle)
            self._replay_index += 1
            
            if self._replay_index < len(self._all_candles):
                time.sleep(max(0.01, interval))  # Min 10ms
        
        self._log("🏁 Replay complete")
    
    @property
    def progress(self) -> float:
        """Get replay progress (0.0 - 1.0)."""
        if not self._all_candles:
            return 1.0
        return self._replay_index / len(self._all_candles)
    
    @property
    def is_complete(self) -> bool:
        """Check if replay is finished."""
        return self._replay_index >= len(self._all_candles)
