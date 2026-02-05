"""
Market Making Module

A market making strategy for ZCash (ZEC-USD) on Coinbase.

Components:
- order_book.py: Fetches real-time bid/ask data from Coinbase
- market_maker.py: Core market making logic with profitability checks
- paper_trading.py: Paper trading runner (simulated execution)
- live_executor.py: Real order execution on Coinbase
- live_trading.py: Live trading runner with web dashboard

Usage:
    # Paper trading (no real money)
    python -m market_making.paper_trading --verbose
    
    # Live trading (REAL MONEY!)
    python -m market_making.live_trading --port 5004
    
    # Test order book fetching
    python -m market_making.order_book

Fee Model:
    - Expected maker fee: 0.025% (0.00025)
    - Minimum spread for breakeven: 0.05% (2 × fee)
    - Minimum spread for profit: 0.05% + min_profit_rate

Error Handling:
    - UnexpectedFeeError: Raised if actual fee differs from expected
    - UnprofitableTradeError: Raised if trade would be unprofitable
    - InsufficientSpreadError: Raised if spread is too tight
"""

from .order_book import CoinbaseOrderBook, OrderBook, OrderBookLevel
from .market_maker import (
    MarketMaker,
    Order,
    OrderSide,
    OrderStatus,
    TradeRound,
    MarketMakerError,
    UnexpectedFeeError,
    UnprofitableTradeError,
    InsufficientSpreadError
)

__all__ = [
    # Order Book
    'CoinbaseOrderBook',
    'OrderBook',
    'OrderBookLevel',
    
    # Market Maker
    'MarketMaker',
    'Order',
    'OrderSide',
    'OrderStatus',
    'TradeRound',
    
    # Exceptions
    'MarketMakerError',
    'UnexpectedFeeError',
    'UnprofitableTradeError',
    'InsufficientSpreadError',
]
