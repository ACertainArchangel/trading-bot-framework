"""
DataFetcher - Unified data fetching from cryptocurrency exchanges.

Handles fetching historical OHLCV candle data with automatic pagination,
rate limiting, and multiple exchange support.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
import requests
import time

from ..core.candle import Candle


class DataFetcher:
    """
    Powerful data fetcher for OHLCV candlestick data.
    
    Supports automatic chunking for large requests, rate limiting,
    and multiple granularities.
    
    Example:
        >>> fetcher = DataFetcher('BTC-USD')
        >>> candles = fetcher.get_candles(days=30, granularity='1h')
        >>> print(f"Got {len(candles)} hourly candles")
    
    Supported Granularities:
        '1m'  - 1 minute
        '5m'  - 5 minutes
        '15m' - 15 minutes
        '1h'  - 1 hour
        '6h'  - 6 hours
        '1d'  - 1 day
    """
    
    BASE_URL = "https://api.exchange.coinbase.com"
    MAX_CANDLES_PER_REQUEST = 300  # Coinbase API limit
    
    GRANULARITIES = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '6h': 21600,
        '1d': 86400
    }
    
    def __init__(
        self,
        product_id: str = "BTC-USD",
        rate_limit_delay: float = 0.1,
        verbose: bool = True
    ):
        """
        Initialize the data fetcher.
        
        Args:
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")
            rate_limit_delay: Delay between API requests (seconds)
            verbose: If True, print progress messages
        """
        self.product_id = product_id
        self.rate_limit_delay = rate_limit_delay
        self.verbose = verbose
        
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'TradingFramework/2.0'})
    
    def _log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)
    
    def get_candles(
        self,
        days: Optional[int] = None,
        months: Optional[int] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        granularity: str = '5m',
        as_objects: bool = True
    ) -> List:
        """
        Fetch historical candle data.
        
        Provide EITHER days/months OR start/end datetime.
        
        Args:
            days: Number of days of history (from now)
            months: Number of months of history (from now)
            start: Start datetime (UTC)
            end: End datetime (UTC), defaults to now
            granularity: Candle size ('1m', '5m', '15m', '1h', '6h', '1d')
            as_objects: If True, return Candle objects; else raw tuples
        
        Returns:
            List of Candle objects (or tuples if as_objects=False)
        
        Examples:
            # Get last 7 days of 1-hour candles
            candles = fetcher.get_candles(days=7, granularity='1h')
            
            # Get last 3 months of 5-minute candles
            candles = fetcher.get_candles(months=3, granularity='5m')
            
            # Get specific date range
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 2, 1, tzinfo=timezone.utc)
            candles = fetcher.get_candles(start=start, end=end, granularity='1h')
        """
        if granularity not in self.GRANULARITIES:
            raise ValueError(
                f"Invalid granularity '{granularity}'. "
                f"Choose from: {list(self.GRANULARITIES.keys())}"
            )
        
        # Determine time range
        now = datetime.now(timezone.utc)
        
        if days is not None:
            end = now
            start = now - timedelta(days=days)
        elif months is not None:
            end = now
            start = now - timedelta(days=months * 30)
        elif start is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end is None:
                end = now
            elif end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        else:
            raise ValueError("Provide either days, months, or start datetime")
        
        if start >= end:
            raise ValueError("Start must be before end")
        
        self._log(f"📦 Fetching {self.product_id} candles...")
        self._log(f"   Period: {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')}")
        self._log(f"   Granularity: {granularity}")
        
        # Fetch data
        raw_candles = self._fetch_range(start, end, granularity)
        
        if not raw_candles:
            self._log("⚠️  No data returned")
            return []
        
        # Sort and deduplicate
        unique = {c[0]: c for c in raw_candles}
        sorted_candles = sorted(unique.values(), key=lambda x: x[0])
        
        self._log(f"✅ Fetched {len(sorted_candles)} candles")
        
        if as_objects:
            return Candle.from_tuples(sorted_candles)
        return sorted_candles
    
    def get_latest(
        self,
        count: int = 100,
        granularity: str = '5m',
        as_objects: bool = True
    ) -> List:
        """
        Fetch the most recent candles.
        
        Args:
            count: Number of candles to fetch
            granularity: Candle size
            as_objects: If True, return Candle objects
        
        Returns:
            List of candles, most recent last
        """
        seconds_per_candle = self.GRANULARITIES[granularity]
        seconds_needed = count * seconds_per_candle * 1.1  # 10% buffer
        days_needed = seconds_needed / 86400
        
        return self.get_candles(
            days=max(1, int(days_needed) + 1),
            granularity=granularity,
            as_objects=as_objects
        )[-count:]
    
    def _fetch_range(
        self,
        start: datetime,
        end: datetime,
        granularity: str
    ) -> List:
        """Fetch data for a time range, chunking if necessary."""
        granularity_seconds = self.GRANULARITIES[granularity]
        total_seconds = (end - start).total_seconds()
        total_candles = int(total_seconds / granularity_seconds)
        
        # Single request if within limit
        if total_candles <= self.MAX_CANDLES_PER_REQUEST:
            return self._fetch_chunk(start, end, granularity_seconds)
        
        # Multiple requests needed
        self._log(f"   Splitting into chunks ({total_candles} candles requested)...")
        
        all_candles = []
        current_start = start
        chunk_duration = timedelta(seconds=granularity_seconds * self.MAX_CANDLES_PER_REQUEST)
        chunk_num = 1
        
        while current_start < end:
            current_end = min(current_start + chunk_duration, end)
            
            chunk = self._fetch_chunk(current_start, current_end, granularity_seconds)
            
            if chunk:
                all_candles.extend(chunk)
                self._log(f"   Chunk {chunk_num}: {len(chunk)} candles")
            
            # Rate limiting
            if current_end < end and self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)
            
            current_start = current_end
            chunk_num += 1
        
        return all_candles
    
    def _fetch_chunk(
        self,
        start: datetime,
        end: datetime,
        granularity_seconds: int,
        max_retries: int = 3
    ) -> List:
        """Fetch a single chunk from the API with retries."""
        url = f"{self.BASE_URL}/products/{self.product_id}/candles"
        params = {
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "granularity": granularity_seconds
        }
        
        for attempt in range(max_retries):
            try:
                response = self._session.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2, 4 seconds
                    self._log(f"⚠️  API error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    self._log(f"❌ API error after {max_retries} attempts: {e}")
                    return []
        return []
    
    def close(self):
        """Close the session."""
        self._session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
