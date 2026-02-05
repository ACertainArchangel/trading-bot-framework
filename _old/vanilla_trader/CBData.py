from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
import requests
import time


class CoinbaseDataFetcher:
    """
    Powerful Coinbase Exchange API client for fetching OHLCV candlestick data.
    
    Supports multiple products, granularities, and efficient batch fetching with
    automatic pagination and rate limiting.
    """
    
    BASE_URL = "https://api.exchange.coinbase.com"
    MAX_CANDLES_PER_REQUEST = 300  # Coinbase API limit
    
    # Supported granularities in seconds
    GRANULARITIES = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '6h': 21600,
        '1d': 86400
    }
    
    def __init__(self, product_id: str = "BTC-USD", rate_limit_delay: float = 0.0):
        """
        Initialize the fetcher.
        
        Args:
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")
            rate_limit_delay: Delay between requests in seconds to avoid rate limits
        """
        self.product_id = product_id
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'CoinbaseDataFetcher/1.0'})
    
    def _normalize_datetime(self, dt: datetime) -> datetime:
        """Convert datetime to UTC if needed."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    def fetch_candles(
        self, 
        start: datetime, 
        end: Optional[datetime] = None,
        granularity: str = '1m'
    ) -> List[Tuple]:
        """
        Fetch OHLCV candles for a specific time range with automatic chunking.
        
        Automatically splits large requests into 300-candle chunks to respect
        API limits and adds rate limiting between requests.
        
        Args:
            start: Start datetime
            end: End datetime (defaults to now if None)
            granularity: Candle size ('1m', '5m', '15m', '1h', '6h', '1d')
        
        Returns:
            List of candles: [[timestamp, low, high, open, close, volume], ...]
            Sorted by timestamp ascending.
        """
        if granularity not in self.GRANULARITIES:
            raise ValueError(f"Invalid granularity. Choose from: {list(self.GRANULARITIES.keys())}")
        
        start = self._normalize_datetime(start)
        end = self._normalize_datetime(end) if end else datetime.now(timezone.utc)
        
        if start >= end:
            raise ValueError("start must be before end")
        
        granularity_seconds = self.GRANULARITIES[granularity]
        
        # Calculate total candles needed
        total_seconds = (end - start).total_seconds()
        total_candles = int(total_seconds / granularity_seconds)
        
        # If within limit, fetch in one request
        if total_candles <= self.MAX_CANDLES_PER_REQUEST:
            candles = self._fetch_chunk(start, end, granularity_seconds)
        else:
            # Chunk into multiple requests
            print(f"📦 Large request detected: {total_candles} candles. Splitting into chunks of {self.MAX_CANDLES_PER_REQUEST}...")
            candles = self._fetch_chunked(start, end, granularity_seconds)
        
        if not candles:
            return []
        
        # Sort and deduplicate by timestamp
        unique_candles = {candle[0]: candle for candle in candles}
        sorted_candles = sorted(unique_candles.values(), key=lambda x: x[0])
        
        print(f"✅ Fetched {len(sorted_candles)} candles total")
        return sorted_candles
    
    def _fetch_chunked(self, start: datetime, end: datetime, granularity: int) -> List[Tuple]:
        """
        Fetch data in chunks of MAX_CANDLES_PER_REQUEST with rate limiting.
        """
        all_candles = []
        current_start = start
        chunk_duration = timedelta(seconds=granularity * self.MAX_CANDLES_PER_REQUEST)
        chunk_num = 1
        
        while current_start < end:
            current_end = min(current_start + chunk_duration, end)
            
            print(f"  Chunk {chunk_num}: {current_start.strftime('%Y-%m-%d %H:%M')} to {current_end.strftime('%Y-%m-%d %H:%M')}")
            
            chunk_candles = self._fetch_chunk(current_start, current_end, granularity)
            
            if chunk_candles:
                all_candles.extend(chunk_candles)
                print(f"    ✓ Got {len(chunk_candles)} candles")
            else:
                print(f"    ⚠ No data returned for this chunk")
            
            # Rate limiting between chunks
            if current_end < end and self.rate_limit_delay > 0:
                print(f"    ⏳ Waiting {self.rate_limit_delay}s for rate limit...")
                time.sleep(self.rate_limit_delay)
            
            current_start = current_end
            chunk_num += 1
        
        return all_candles
    
    def _fetch_chunk(self, start: datetime, end: datetime, granularity: int) -> List[Tuple]:
        """Fetch a single chunk from the API."""
        url = f"{self.BASE_URL}/products/{self.product_id}/candles"
        params = {
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "granularity": granularity
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")
            return []
    
    def fetch_latest(self, count: int = 100, granularity: str = '1m') -> List[Tuple]:
        """
        Fetch the most recent candles.
        
        Args:
            count: Number of candles to fetch
            granularity: Candle size
        
        Returns:
            List of recent candles
        """
        granularity_seconds = self.GRANULARITIES[granularity]
        end = datetime.now(timezone.utc)
        start = end - timedelta(seconds=granularity_seconds * count)
        
        return self.fetch_candles(start, end, granularity)
    
    def fetch_date_range(
        self, 
        start_date: str, 
        end_date: str, 
        granularity: str = '1m'
    ) -> List[Tuple]:
        """
        Fetch candles for a date range (convenience method).
        
        Args:
            start_date: ISO format date string (e.g., "2021-01-01")
            end_date: ISO format date string
            granularity: Candle size
        
        Returns:
            List of candles
        """
        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        
        return self.fetch_candles(start, end, granularity)


# Legacy compatibility functions
def fetch_300_btc(start: datetime):
    """Legacy function - use CoinbaseDataFetcher instead."""
    fetcher = CoinbaseDataFetcher()
    end = start + timedelta(minutes=300)
    return fetcher.fetch_candles(start, end, '1m')


def fetch_from_until_now(start: datetime):
    """Legacy function - use CoinbaseDataFetcher instead."""
    fetcher = CoinbaseDataFetcher()
    return fetcher.fetch_candles(start, None, '1m')

if __name__ == "__main__":
    # Example 1: Fetch recent data
    fetcher = CoinbaseDataFetcher(product_id="BTC-USD")
    
    print("=" * 60)
    print("Example 1: Fetch last 100 1-minute candles")
    print("=" * 60)
    recent_data = fetcher.fetch_latest(count=100, granularity='1m')
    print(f"Fetched {len(recent_data)} recent candles")
    print(f"First candle: {recent_data[0]}")
    print(f"Last candle: {recent_data[-1]}")
    
    # Example 2: Fetch specific date range
    print("\n" + "=" * 60)
    print("Example 2: Fetch data for January 1-2, 2021 (5-minute candles)")
    print("=" * 60)
    start = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2021, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    data = fetcher.fetch_candles(start, end, granularity='5m')
    print(f"Fetched {len(data)} candles")
    print(f"First 3 candles:")
    for candle in data[:3]:
        ts = datetime.fromtimestamp(candle[0], tz=timezone.utc)
        print(f"  {ts}: Open={candle[3]}, Close={candle[4]}, Volume={candle[5]}")
    
    # Example 3: Multiple products
    print("\n" + "=" * 60)
    print("Example 3: Fetch ETH-USD hourly data")
    print("=" * 60)
    eth_fetcher = CoinbaseDataFetcher(product_id="ETH-USD")
    eth_data = eth_fetcher.fetch_latest(count=24, granularity='1h')
    print(f"Fetched {len(eth_data)} hourly ETH candles")
    
    print("\n✅ All examples completed successfully!")
