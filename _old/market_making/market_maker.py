"""
Market Maker Core Logic

Implements market making strategy:
1. Fetch spread data from exchange (bid/ask prices) for ZEC-USD
2. Calculate if executing a buy and sell at spread would be profitable after fees
3. If profitable, place buy and sell limit orders simultaneously
4. Monitor for fills and handle partial executions
5. Track P&L and positions
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Callable, Tuple
from enum import Enum
import time
import uuid

try:
    from .order_book import CoinbaseOrderBook, OrderBook
except ImportError:
    from order_book import CoinbaseOrderBook, OrderBook


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Order:
    """Represents a limit order"""
    id: str
    side: OrderSide
    price: float
    size: float
    product_id: str
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    filled_value: float = 0.0
    fees: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    
    @property
    def remaining_size(self) -> float:
        return self.size - self.filled_size
    
    @property
    def average_fill_price(self) -> float:
        return self.filled_value / self.filled_size if self.filled_size > 0 else 0.0
    
    def __str__(self) -> str:
        return (f"Order({self.side.value} {self.size:.4f} @ ${self.price:.4f}, "
                f"status={self.status.value}, filled={self.filled_size:.4f})")


@dataclass
class TradeRound:
    """
    Represents a complete market-making round: buy and sell.
    
    A profitable round:
    1. Buy at/near best bid (lower price)
    2. Sell at/near best ask (higher price)
    3. Profit = (sell_proceeds - buy_cost) - total_fees
    """
    id: str
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    @property
    def is_complete(self) -> bool:
        """Both orders filled"""
        return (self.buy_order and self.buy_order.status == OrderStatus.FILLED and
                self.sell_order and self.sell_order.status == OrderStatus.FILLED)
    
    @property
    def gross_profit(self) -> float:
        """Profit before fees"""
        if not (self.buy_order and self.sell_order):
            return 0.0
        # Sell proceeds - buy cost
        return self.sell_order.filled_value - self.buy_order.filled_value
    
    @property
    def total_fees(self) -> float:
        """Total fees paid"""
        fees = 0.0
        if self.buy_order:
            fees += self.buy_order.fees
        if self.sell_order:
            fees += self.sell_order.fees
        return fees
    
    @property
    def net_profit(self) -> float:
        """Profit after fees"""
        return self.gross_profit - self.total_fees
    
    @property
    def net_profit_percent(self) -> float:
        """Net profit as percentage of buy value"""
        if self.buy_order and self.buy_order.filled_value > 0:
            return (self.net_profit / self.buy_order.filled_value) * 100
        return 0.0
    
    def __str__(self) -> str:
        status = "complete" if self.is_complete else "incomplete"
        return f"TradeRound({self.id[:8]}): {status}, net_profit=${self.net_profit:.4f} ({self.net_profit_percent:.4f}%)"


class MarketMakerError(Exception):
    """Base exception for market maker errors"""
    pass


class UnexpectedFeeError(MarketMakerError):
    """Raised when actual fee differs from expected"""
    def __init__(self, expected: float, actual: float, tolerance: float):
        self.expected = expected
        self.actual = actual
        self.tolerance = tolerance
        super().__init__(
            f"Unexpected fee rate! Expected {expected*100:.4f}%, "
            f"got {actual*100:.4f}% (tolerance: {tolerance*100:.4f}%)"
        )


class UnprofitableTradeError(MarketMakerError):
    """Raised when a proposed trade would be unprofitable"""
    def __init__(self, expected_profit: float, message: str = ""):
        self.expected_profit = expected_profit
        msg = f"Unprofitable trade! Expected profit: ${expected_profit:.4f}"
        if message:
            msg += f" - {message}"
        super().__init__(msg)


class InsufficientSpreadError(MarketMakerError):
    """Raised when spread is too tight to make profit"""
    def __init__(self, spread_pct: float, min_required: float):
        self.spread_pct = spread_pct
        self.min_required = min_required
        super().__init__(
            f"Spread too tight! Current: {spread_pct:.4f}%, "
            f"Required for profit: {min_required:.4f}%"
        )


class MarketMaker:
    """
    Market Maker Core Logic
    
    Places simultaneous buy and sell orders around the mid-price,
    profiting from the bid-ask spread minus fees.
    
    Fee Model:
    - Expected maker fee: 0.025% (0.00025)
    - We pay fee on both buy AND sell sides
    - Minimum profitable spread: 2 * fee_rate = 0.05%
    
    Error Handling:
    - Errors if actual fee differs from expected by more than fee_tolerance
    - Errors if proposed trade would be unprofitable
    """
    
    def __init__(
        self,
        product_id: str = "ZEC-USD",
        fee_rate: float = 0.00025,  # 0.025% maker fee
        fee_tolerance: float = 0.0001,  # Allow 0.01% variance
        min_profit_rate: float = 0.0001,  # Minimum 0.01% profit per round
        trade_size_usd: float = 100.0,  # Size per trade in USD
        max_position_usd: float = 1000.0,  # Maximum position size
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize market maker.
        
        Args:
            product_id: Trading pair (e.g., "ZEC-USD")
            fee_rate: Expected maker fee rate (0.00025 = 0.025%)
            fee_tolerance: Maximum acceptable fee rate variance
            min_profit_rate: Minimum profit rate per round to execute
            trade_size_usd: Size of each trade in USD
            max_position_usd: Maximum USD value of position to hold
            logger: Optional logging callback
        """
        self.product_id = product_id
        self.fee_rate = fee_rate
        self.fee_tolerance = fee_tolerance
        self.min_profit_rate = min_profit_rate
        self.trade_size_usd = trade_size_usd
        self.max_position_usd = max_position_usd
        self._log = logger or print
        
        # Order book fetcher
        self.order_book = CoinbaseOrderBook(product_id=product_id)
        
        # Position tracking
        self.usd_balance: float = 0.0
        self.asset_balance: float = 0.0
        self.initial_usd: float = 0.0
        
        # Trade history
        self.active_round: Optional[TradeRound] = None
        self.completed_rounds: List[TradeRound] = []
        self.all_orders: List[Order] = []
        
        # Stats
        self.total_trades = 0
        self.profitable_trades = 0
        self.total_profit = 0.0
        self.total_fees = 0.0
        
        # Calculate minimum spread required for profitability
        # We pay fee on BOTH sides, so minimum spread = 2 * fee_rate
        self.min_spread_for_breakeven = 2 * self.fee_rate
        self.min_spread_for_profit = self.min_spread_for_breakeven + self.min_profit_rate
        
        self._log(f"🏦 Market Maker initialized for {product_id}")
        self._log(f"   Fee Rate: {fee_rate*100:.4f}% (tolerance: {fee_tolerance*100:.4f}%)")
        self._log(f"   Min Spread for Breakeven: {self.min_spread_for_breakeven*100:.4f}%")
        self._log(f"   Min Spread for Profit: {self.min_spread_for_profit*100:.4f}%")
    
    def set_balances(self, usd: float, asset: float):
        """Set initial balances"""
        self.usd_balance = usd
        self.asset_balance = asset
        if self.initial_usd == 0:
            self.initial_usd = usd
        self._log(f"💰 Balances: ${usd:.2f} USD, {asset:.4f} {self.product_id.split('-')[0]}")
    
    def validate_fee_rate(self, actual_fee_rate: float):
        """
        Validate that actual fee matches expected.
        
        Raises:
            UnexpectedFeeError: If fee differs by more than tolerance
        """
        diff = abs(actual_fee_rate - self.fee_rate)
        if diff > self.fee_tolerance:
            raise UnexpectedFeeError(
                expected=self.fee_rate,
                actual=actual_fee_rate,
                tolerance=self.fee_tolerance
            )
    
    def calculate_profitability(self, book: OrderBook, trade_size_usd: Optional[float] = None) -> Dict:
        """
        Calculate if market making would be profitable with current spread.
        
        Args:
            book: Current order book
            trade_size_usd: Size of trade in USD (default: self.trade_size_usd)
        
        Returns:
            Dict with profitability analysis
        
        Raises:
            ValueError: If order book is empty
        """
        if not book.best_bid or not book.best_ask:
            raise ValueError("Order book is empty")
        
        size = trade_size_usd or self.trade_size_usd
        
        bid_price = book.best_bid.price
        ask_price = book.best_ask.price
        spread = ask_price - bid_price
        spread_pct = (spread / book.mid_price) * 100
        
        # Calculate trade quantities
        # We BUY at/near bid (lower price) and SELL at/near ask (higher price)
        buy_size_asset = size / bid_price  # ZEC we'd receive
        buy_cost = size  # USD we spend
        buy_fee = buy_cost * self.fee_rate
        
        sell_proceeds_gross = buy_size_asset * ask_price
        sell_fee = sell_proceeds_gross * self.fee_rate
        sell_proceeds_net = sell_proceeds_gross - sell_fee
        
        # Net result
        total_fees = buy_fee + sell_fee
        gross_profit = sell_proceeds_gross - buy_cost
        net_profit = gross_profit - total_fees
        net_profit_pct = (net_profit / buy_cost) * 100
        
        # Is it profitable?
        is_profitable = net_profit > 0
        meets_minimum = net_profit_pct >= (self.min_profit_rate * 100)
        
        return {
            "is_profitable": is_profitable,
            "meets_minimum_profit": meets_minimum,
            "bid_price": bid_price,
            "ask_price": ask_price,
            "mid_price": book.mid_price,
            "spread": spread,
            "spread_pct": spread_pct,
            "trade_size_usd": size,
            "buy_size_asset": buy_size_asset,
            "buy_fee": buy_fee,
            "sell_fee": sell_fee,
            "total_fees": total_fees,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "min_spread_required": self.min_spread_for_profit * 100
        }
    
    def check_profitability(self) -> Dict:
        """
        Check if current market conditions are profitable.
        
        Returns:
            Profitability analysis dict
            
        Raises:
            InsufficientSpreadError: If spread is too tight
            UnprofitableTradeError: If trade would be unprofitable
        """
        book = self.order_book.fetch_order_book(limit=10)
        analysis = self.calculate_profitability(book)
        
        if not analysis["is_profitable"]:
            raise UnprofitableTradeError(
                expected_profit=analysis["net_profit"],
                message=f"Spread {analysis['spread_pct']:.4f}% < minimum {analysis['min_spread_required']:.4f}%"
            )
        
        if not analysis["meets_minimum_profit"]:
            raise InsufficientSpreadError(
                spread_pct=analysis["spread_pct"],
                min_required=self.min_spread_for_profit * 100
            )
        
        return analysis
    
    def create_order(
        self,
        side: OrderSide,
        price: float,
        size: float
    ) -> Order:
        """
        Create a new order (does not execute).
        
        Args:
            side: BUY or SELL
            price: Limit price
            size: Amount of asset
        
        Returns:
            Order object
        """
        order = Order(
            id=str(uuid.uuid4()),
            side=side,
            price=price,
            size=size,
            product_id=self.product_id
        )
        self.all_orders.append(order)
        return order
    
    def start_trade_round(self, analysis: Dict) -> Tuple[Order, Order]:
        """
        Start a new trading round with buy and sell orders.
        
        Args:
            analysis: Profitability analysis from check_profitability()
        
        Returns:
            Tuple of (buy_order, sell_order)
            
        Raises:
            UnprofitableTradeError: If trade would be unprofitable
            ValueError: If there's already an active round
        """
        if self.active_round:
            raise ValueError("Active round already in progress")
        
        # Double-check profitability before creating orders
        if not analysis["is_profitable"] or not analysis["meets_minimum_profit"]:
            raise UnprofitableTradeError(
                expected_profit=analysis["net_profit"],
                message="Trade doesn't meet profitability requirements"
            )
        
        # Verify we have enough balance
        if self.usd_balance < analysis["trade_size_usd"]:
            raise ValueError(
                f"Insufficient USD balance: ${self.usd_balance:.2f} < ${analysis['trade_size_usd']:.2f}"
            )
        
        # Create orders
        buy_order = self.create_order(
            side=OrderSide.BUY,
            price=analysis["bid_price"],
            size=analysis["buy_size_asset"]
        )
        
        sell_order = self.create_order(
            side=OrderSide.SELL,
            price=analysis["ask_price"],
            size=analysis["buy_size_asset"]
        )
        
        # Create trade round
        self.active_round = TradeRound(
            id=str(uuid.uuid4()),
            buy_order=buy_order,
            sell_order=sell_order
        )
        
        self._log(f"📤 Started trade round {self.active_round.id[:8]}")
        self._log(f"   BUY: {buy_order}")
        self._log(f"   SELL: {sell_order}")
        self._log(f"   Expected profit: ${analysis['net_profit']:.4f} ({analysis['net_profit_pct']:.4f}%)")
        
        return (buy_order, sell_order)
    
    def simulate_fill(
        self,
        order: Order,
        fill_price: Optional[float] = None,
        fee_rate: Optional[float] = None
    ):
        """
        Simulate an order fill (for paper trading).
        
        Args:
            order: Order to fill
            fill_price: Price filled at (default: order.price)
            fee_rate: Fee rate applied (default: self.fee_rate)
            
        Raises:
            UnexpectedFeeError: If fee rate doesn't match expected
        """
        fill_price = fill_price or order.price
        actual_fee_rate = fee_rate if fee_rate is not None else self.fee_rate
        
        # Validate fee
        self.validate_fee_rate(actual_fee_rate)
        
        # Calculate fill
        order.filled_size = order.size
        order.filled_value = order.filled_size * fill_price
        order.fees = order.filled_value * actual_fee_rate
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.utcnow()
        
        # Update balances
        if order.side == OrderSide.BUY:
            # Spend USD, receive asset
            self.usd_balance -= (order.filled_value + order.fees)
            self.asset_balance += order.filled_size
        else:
            # Spend asset, receive USD
            self.asset_balance -= order.filled_size
            self.usd_balance += (order.filled_value - order.fees)
        
        self._log(f"✅ Filled {order.side.value.upper()}: {order.filled_size:.4f} @ ${fill_price:.4f}, fees=${order.fees:.4f}")
    
    def complete_round(self):
        """Complete the active trade round and record stats."""
        if not self.active_round:
            return
        
        if not self.active_round.is_complete:
            self._log(f"⚠️  Round {self.active_round.id[:8]} incomplete")
            return
        
        self.active_round.completed_at = datetime.utcnow()
        
        # Update stats
        self.total_trades += 1
        self.total_profit += self.active_round.net_profit
        self.total_fees += self.active_round.total_fees
        
        if self.active_round.net_profit > 0:
            self.profitable_trades += 1
        
        self._log(f"🏁 Completed round {self.active_round.id[:8]}")
        self._log(f"   Net Profit: ${self.active_round.net_profit:.4f} ({self.active_round.net_profit_percent:.4f}%)")
        self._log(f"   Fees: ${self.active_round.total_fees:.4f}")
        
        self.completed_rounds.append(self.active_round)
        self.active_round = None
    
    def get_stats(self) -> Dict:
        """Get performance statistics."""
        win_rate = (self.profitable_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # Calculate current portfolio value
        book = self.order_book.fetch_order_book(limit=1)
        asset_value_usd = self.asset_balance * book.mid_price if book.mid_price else 0
        total_portfolio = self.usd_balance + asset_value_usd
        
        return {
            "product_id": self.product_id,
            "total_trades": self.total_trades,
            "profitable_trades": self.profitable_trades,
            "win_rate": win_rate,
            "total_profit": self.total_profit,
            "total_fees": self.total_fees,
            "usd_balance": self.usd_balance,
            "asset_balance": self.asset_balance,
            "asset_value_usd": asset_value_usd,
            "total_portfolio_usd": total_portfolio,
            "initial_usd": self.initial_usd,
            "pnl_usd": total_portfolio - self.initial_usd,
            "pnl_pct": ((total_portfolio / self.initial_usd) - 1) * 100 if self.initial_usd > 0 else 0
        }
    
    def print_stats(self):
        """Print formatted statistics."""
        stats = self.get_stats()
        print()
        print("=" * 50)
        print("📊 MARKET MAKER STATISTICS")
        print("=" * 50)
        print(f"Product: {stats['product_id']}")
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Profitable: {stats['profitable_trades']} ({stats['win_rate']:.1f}%)")
        print(f"Total Profit: ${stats['total_profit']:.4f}")
        print(f"Total Fees: ${stats['total_fees']:.4f}")
        print("-" * 50)
        print(f"USD Balance: ${stats['usd_balance']:.2f}")
        print(f"Asset Balance: {stats['asset_balance']:.4f}")
        print(f"Asset Value: ${stats['asset_value_usd']:.2f}")
        print(f"Total Portfolio: ${stats['total_portfolio_usd']:.2f}")
        print("-" * 50)
        print(f"Initial USD: ${stats['initial_usd']:.2f}")
        print(f"P&L: ${stats['pnl_usd']:.2f} ({stats['pnl_pct']:.2f}%)")
        print("=" * 50)


def test_market_maker():
    """Test market maker logic with paper trading."""
    print("🧪 Testing Market Maker Core Logic")
    print("=" * 60)
    
    mm = MarketMaker(
        product_id="ZEC-USD",
        fee_rate=0.00025,  # 0.025%
        min_profit_rate=0.0001,  # 0.01% minimum profit
        trade_size_usd=50.0
    )
    
    # Set starting balances
    mm.set_balances(usd=1000.0, asset=0.0)
    
    print()
    print("📈 Checking market conditions...")
    
    try:
        analysis = mm.check_profitability()
        print(f"✅ Market is tradeable!")
        print(f"   Spread: {analysis['spread_pct']:.4f}%")
        print(f"   Expected Profit: ${analysis['net_profit']:.4f} ({analysis['net_profit_pct']:.4f}%)")
        print()
        
        # Start a trade round
        buy_order, sell_order = mm.start_trade_round(analysis)
        
        # Simulate fills
        print()
        print("📋 Simulating order fills...")
        mm.simulate_fill(buy_order)
        mm.simulate_fill(sell_order)
        
        # Complete round
        mm.complete_round()
        
    except (UnprofitableTradeError, InsufficientSpreadError) as e:
        print(f"⚠️  Cannot trade: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Print stats
    mm.print_stats()


if __name__ == "__main__":
    test_market_maker()