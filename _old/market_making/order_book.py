"""
Order Book Fetcher for Coinbase Advanced Trade API

Fetches real-time bid/ask data from Coinbase for market making.
Supports ZEC-USD and other trading pairs.
"""

import requests
from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime


@dataclass
class OrderBookLevel:
    """Single price level in the order book"""
    price: float
    size: float
    
    @property
    def value(self) -> float:
        """Total value at this level (price * size)"""
        return self.price * self.size


@dataclass
class OrderBook:
    """
    Order book snapshot with bids and asks.
    
    Bids are sorted highest to lowest (best bid first).
    Asks are sorted lowest to highest (best ask first).
    """
    product_id: str
    bids: List[OrderBookLevel]  # Highest to lowest
    asks: List[OrderBookLevel]  # Lowest to highest
    timestamp: datetime
    
    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """Best (highest) bid price"""
        return self.bids[0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """Best (lowest) ask price"""
        return self.asks[0] if self.asks else None
    
    @property
    def mid_price(self) -> Optional[float]:
        """Mid-market price (average of best bid and ask)"""
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / 2
        return None
    
    @property
    def spread(self) -> Optional[float]:
        """Absolute spread (best ask - best bid)"""
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None
    
    @property
    def spread_percent(self) -> Optional[float]:
        """Spread as percentage of mid price"""
        if self.mid_price and self.spread:
            return (self.spread / self.mid_price) * 100
        return None
    
    def __str__(self) -> str:
        if self.best_bid and self.best_ask:
            return (f"OrderBook({self.product_id}): "
                    f"Bid ${self.best_bid.price:.4f} x {self.best_bid.size:.4f} | "
                    f"Ask ${self.best_ask.price:.4f} x {self.best_ask.size:.4f} | "
                    f"Spread {self.spread_percent:.4f}%")
        return f"OrderBook({self.product_id}): No data"


class CoinbaseOrderBook:
    """
    Fetches order book data from Coinbase Advanced Trade API.
    
    Uses public endpoints - no authentication required for order book data.
    """
    
    def __init__(self, product_id: str = "ZEC-USD"):
        """
        Initialize order book fetcher.
        
        Args:
            product_id: Trading pair (e.g., "ZEC-USD", "BTC-USD")
        """
        self.product_id = product_id
        self.base_url = "https://api.coinbase.com"
        self._last_book: Optional[OrderBook] = None
    
    def fetch_order_book(self, level: int = 2, limit: int = 50) -> OrderBook:
        """
        Fetch current order book from Coinbase.
        
        Args:
            level: Book detail level (1=best only, 2=top 50, 3=full book)
            limit: Number of levels to fetch (max 500 for public API)
        
        Returns:
            OrderBook with current bids and asks
            
        Raises:
            ConnectionError: If API request fails
            ValueError: If response is invalid
        """
        # Use the public product book endpoint
        endpoint = f"/api/v3/brokerage/market/product_book"
        params = {
            "product_id": self.product_id,
            "limit": min(limit, 500)
        }
        
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to fetch order book: {e}")
        
        # Parse the response
        pricebook = data.get('pricebook', {})
        
        # Parse bids (buyers) - comes as list of {"price": "...", "size": "..."}
        bids = []
        for bid in pricebook.get('bids', []):
            price = float(bid.get('price', 0))
            size = float(bid.get('size', 0))
            if price > 0 and size > 0:
                bids.append(OrderBookLevel(price=price, size=size))
        
        # Parse asks (sellers)
        asks = []
        for ask in pricebook.get('asks', []):
            price = float(ask.get('price', 0))
            size = float(ask.get('size', 0))
            if price > 0 and size > 0:
                asks.append(OrderBookLevel(price=price, size=size))
        
        # Sort: bids highest first, asks lowest first
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price, reverse=False)
        
        # Parse timestamp
        time_str = pricebook.get('time', '')
        try:
            timestamp = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            timestamp = datetime.utcnow()
        
        book = OrderBook(
            product_id=self.product_id,
            bids=bids,
            asks=asks,
            timestamp=timestamp
        )
        
        self._last_book = book
        return book
    
    def get_best_prices(self) -> Tuple[float, float]:
        """
        Get best bid and ask prices.
        
        Returns:
            Tuple of (best_bid_price, best_ask_price)
            
        Raises:
            ValueError: If order book is empty
        """
        book = self.fetch_order_book(level=1, limit=1)
        
        if not book.best_bid or not book.best_ask:
            raise ValueError(f"No order book data for {self.product_id}")
        
        return (book.best_bid.price, book.best_ask.price)
    
    def calculate_market_impact(self, side: str, size: float) -> Tuple[float, float]:
        """
        Calculate the price impact of executing a market order.
        
        Args:
            side: "buy" or "sell"
            size: Amount of base currency to trade
        
        Returns:
            Tuple of (average_price, total_cost)
            
        Raises:
            ValueError: If insufficient liquidity
        """
        book = self.fetch_order_book(limit=100)
        
        if side.lower() == "buy":
            # Buying eats into asks (we pay ask prices)
            levels = book.asks
        else:
            # Selling eats into bids (we receive bid prices)
            levels = book.bids
        
        remaining = size
        total_value = 0.0
        total_size = 0.0
        
        for level in levels:
            if remaining <= 0:
                break
            
            take_size = min(remaining, level.size)
            total_value += take_size * level.price
            total_size += take_size
            remaining -= take_size
        
        if remaining > 0:
            raise ValueError(
                f"Insufficient liquidity for {size} {self.product_id.split('-')[0]}. "
                f"Only {total_size:.4f} available."
            )
        
        avg_price = total_value / total_size if total_size > 0 else 0
        return (avg_price, total_value)
    
    @property
    def last_book(self) -> Optional[OrderBook]:
        """Last fetched order book (may be stale)"""
        return self._last_book


def test_order_book():
    """Test order book fetching for ZEC-USD"""
    print("🧪 Testing Order Book Fetcher")
    print("=" * 60)
    
    fetcher = CoinbaseOrderBook(product_id="ZEC-USD")
    
    try:
        book = fetcher.fetch_order_book(limit=10)
        print(f"✅ Successfully fetched order book")
        print(f"📊 {book}")
        print()
        
        print(f"📈 Best Bid: ${book.best_bid.price:.4f} ({book.best_bid.size:.4f} ZEC)")
        print(f"📉 Best Ask: ${book.best_ask.price:.4f} ({book.best_ask.size:.4f} ZEC)")
        print(f"📏 Spread: ${book.spread:.4f} ({book.spread_percent:.4f}%)")
        print(f"🎯 Mid Price: ${book.mid_price:.4f}")
        print()
        
        # Test market impact
        print("🔍 Market Impact Analysis (buying 10 ZEC):")
        avg_price, total_cost = fetcher.calculate_market_impact("buy", 10)
        print(f"   Average Price: ${avg_price:.4f}")
        print(f"   Total Cost: ${total_cost:.2f}")
        print()
        
        print("🔍 Market Impact Analysis (selling 10 ZEC):")
        avg_price, total_proceeds = fetcher.calculate_market_impact("sell", 10)
        print(f"   Average Price: ${avg_price:.4f}")
        print(f"   Total Proceeds: ${total_proceeds:.2f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_order_book()
