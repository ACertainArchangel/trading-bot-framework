"""
Candle - The fundamental unit of market data.

A candle represents price action over a specific time period (1m, 5m, 1h, etc.)
and contains the open, high, low, close prices plus volume.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple, List


@dataclass(frozen=True, slots=True)
class Candle:
    """
    OHLCV candlestick data.
    
    Attributes:
        timestamp: Unix timestamp (seconds since epoch)
        open: Opening price
        high: Highest price during period
        low: Lowest price during period  
        close: Closing price
        volume: Trading volume
    
    Example:
        >>> candle = Candle(1706900400, 42000.0, 42500.0, 41800.0, 42300.0, 150.5)
        >>> candle.close
        42300.0
        >>> candle.datetime
        datetime(2024, 2, 2, 19, 0, tzinfo=timezone.utc)
    """
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime object."""
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)
    
    @property
    def is_bullish(self) -> bool:
        """True if close > open (green candle)."""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """True if close < open (red candle)."""
        return self.close < self.open
    
    @property
    def body_size(self) -> float:
        """Size of the candle body (absolute difference between open and close)."""
        return abs(self.close - self.open)
    
    @property
    def upper_wick(self) -> float:
        """Size of upper wick."""
        return self.high - max(self.open, self.close)
    
    @property
    def lower_wick(self) -> float:
        """Size of lower wick."""
        return min(self.open, self.close) - self.low
    
    @property
    def range(self) -> float:
        """Total price range (high - low)."""
        return self.high - self.low
    
    def body_percent(self) -> float:
        """Body size as percentage of total range."""
        if self.range == 0:
            return 0.0
        return (self.body_size / self.range) * 100
    
    @classmethod
    def from_tuple(cls, data: Tuple) -> 'Candle':
        """
        Create a Candle from raw API tuple format.
        
        The Coinbase API returns: [timestamp, low, high, open, close, volume]
        """
        return cls(
            timestamp=int(data[0]),
            low=float(data[1]),
            high=float(data[2]),
            open=float(data[3]),
            close=float(data[4]),
            volume=float(data[5])
        )
    
    @classmethod
    def from_tuples(cls, data: List[Tuple]) -> List['Candle']:
        """Convert a list of raw tuples to Candle objects."""
        return [cls.from_tuple(t) for t in data]
    
    def to_tuple(self) -> Tuple:
        """Convert back to raw tuple format (Coinbase API format)."""
        return (self.timestamp, self.low, self.high, self.open, self.close, self.volume)
    
    def __str__(self) -> str:
        dt_str = self.datetime.strftime("%Y-%m-%d %H:%M")
        direction = "🟢" if self.is_bullish else "🔴"
        return f"{direction} {dt_str} | O:{self.open:.2f} H:{self.high:.2f} L:{self.low:.2f} C:{self.close:.2f} V:{self.volume:.2f}"
