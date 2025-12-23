"""
Paper trading interface for testing aggressive strategies with SL/TP.

Simulates order execution including:
- Market and limit orders
- Stop orders (for stop-loss)
- Take profit orders
- Partial fills simulation (optional)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Callable
from enum import Enum
import uuid


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(Enum):
    PENDING = "PENDING"       # Order placed but not active
    OPEN = "OPEN"             # Order active in market
    FILLED = "FILLED"         # Fully filled
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class SimulatedOrder:
    """Simulated order for paper trading."""
    order_id: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None       # Limit price
    stop_price: Optional[float] = None  # Stop trigger price
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_size: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'order_id': self.order_id,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'size': self.size,
            'price': self.price,
            'stop_price': self.stop_price,
            'status': self.status.value,
            'filled_price': self.filled_price,
            'filled_size': self.filled_size,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
        }


class PaperTradingInterface:
    """
    Simulates exchange for paper trading with full order book.
    
    Features:
    - Simulates market, limit, stop, and stop-limit orders
    - Tracks balances (currency and asset)
    - Applies fees on fills
    - Triggers stop orders when price crosses threshold
    """
    
    def __init__(self, 
                 initial_currency: float = 1000.0,
                 initial_asset: float = 0.0,
                 fee_rate: float = 0.0025,
                 pair: str = "BTC-USD",
                 logger: Callable[[str], None] = None):
        """
        Args:
            initial_currency: Starting USD balance
            initial_asset: Starting crypto balance
            fee_rate: Trading fee as decimal (0.0025 = 0.25%)
            pair: Trading pair
            logger: Logging function
        """
        self.pair = pair
        self.fee_rate = fee_rate
        self._log = logger or (lambda x: None)
        
        # Balances
        self._currency = initial_currency
        self._asset = initial_asset
        self._initial_currency = initial_currency
        self._initial_asset = initial_asset
        
        # Order book
        self.orders: Dict[str, SimulatedOrder] = {}
        self.filled_orders: List[SimulatedOrder] = []
        
        # Current market price (updated externally)
        self._current_price: float = 0.0
        
        # Trade history for dashboard
        self.trade_history: List[dict] = []
    
    @property
    def currency(self) -> float:
        """Current USD balance."""
        return self._currency
    
    @property
    def asset(self) -> float:
        """Current crypto balance."""
        return self._asset
    
    @property
    def current_price(self) -> float:
        """Current market price."""
        return self._current_price
    
    def update_price(self, price: float) -> List[SimulatedOrder]:
        """
        Update market price and check for order fills.
        
        Args:
            price: New market price
            
        Returns:
            List of orders that were filled this tick
        """
        old_price = self._current_price
        self._current_price = price
        
        filled_this_tick = []
        
        # Check all open orders
        orders_to_check = [o for o in self.orders.values() 
                          if o.status in (OrderStatus.PENDING, OrderStatus.OPEN)]
        
        for order in orders_to_check:
            filled = self._check_order_fill(order, old_price, price)
            if filled:
                filled_this_tick.append(order)
        
        return filled_this_tick
    
    def _check_order_fill(self, order: SimulatedOrder, 
                          old_price: float, new_price: float) -> bool:
        """Check if order should be filled based on price movement."""
        
        # Market orders fill immediately
        if order.order_type == OrderType.MARKET:
            return self._fill_order(order, new_price)
        
        # Limit orders
        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                # Buy limit fills when price drops to or below limit
                if new_price <= order.price:
                    return self._fill_order(order, order.price)
            else:  # SELL
                # Sell limit fills when price rises to or above limit
                if new_price >= order.price:
                    return self._fill_order(order, order.price)
        
        # Stop orders (for stop-loss)
        if order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY:
                # Buy stop triggers when price rises above stop
                if old_price < order.stop_price <= new_price:
                    return self._fill_order(order, new_price)
            else:  # SELL
                # Sell stop triggers when price falls below stop
                if old_price > order.stop_price >= new_price:
                    return self._fill_order(order, new_price)
        
        # Stop-limit orders
        if order.order_type == OrderType.STOP_LIMIT:
            triggered = False
            if order.side == OrderSide.BUY:
                if old_price < order.stop_price <= new_price:
                    triggered = True
            else:
                if old_price > order.stop_price >= new_price:
                    triggered = True
            
            if triggered:
                # Convert to limit order
                order.order_type = OrderType.LIMIT
                order.status = OrderStatus.OPEN
                # Check if limit can fill immediately
                return self._check_order_fill(order, old_price, new_price)
        
        return False
    
    def _fill_order(self, order: SimulatedOrder, fill_price: float) -> bool:
        """Execute order fill."""
        fee = order.size * fill_price * self.fee_rate
        
        if order.side == OrderSide.BUY:
            cost = order.size * fill_price + fee
            if cost > self._currency:
                self._log(f"⚠️ Insufficient funds for buy: need ${cost:.2f}, have ${self._currency:.2f}")
                order.status = OrderStatus.REJECTED
                return False
            
            self._currency -= cost
            self._asset += order.size
            
        else:  # SELL
            if order.size > self._asset:
                self._log(f"⚠️ Insufficient asset for sell: need {order.size}, have {self._asset}")
                order.status = OrderStatus.REJECTED
                return False
            
            revenue = order.size * fill_price - fee
            self._currency += revenue
            self._asset -= order.size
        
        # Update order state
        order.status = OrderStatus.FILLED
        order.filled_price = fill_price
        order.filled_size = order.size
        order.filled_at = datetime.utcnow()
        
        # Move to filled orders
        if order.order_id in self.orders:
            del self.orders[order.order_id]
        self.filled_orders.append(order)
        
        # Record trade
        self.trade_history.append({
            'timestamp': order.filled_at.timestamp() * 1000,
            'side': order.side.value,
            'price': fill_price,
            'size': order.size,
            'order_type': order.order_type.value,
            'order_id': order.order_id,
        })
        
        side_emoji = "🟢" if order.side == OrderSide.BUY else "🔴"
        self._log(f"{side_emoji} FILLED: {order.side.value} {order.size:.6f} @ ${fill_price:.2f}")
        
        return True
    
    def place_market_order(self, side: OrderSide, size: float) -> SimulatedOrder:
        """Place a market order (fills immediately)."""
        order = SimulatedOrder(
            order_id=str(uuid.uuid4())[:8],
            side=side,
            order_type=OrderType.MARKET,
            size=size,
            status=OrderStatus.OPEN,
        )
        self.orders[order.order_id] = order
        
        # Market orders fill immediately at current price
        self._fill_order(order, self._current_price)
        return order
    
    def place_limit_order(self, side: OrderSide, size: float, 
                          price: float) -> SimulatedOrder:
        """Place a limit order."""
        order = SimulatedOrder(
            order_id=str(uuid.uuid4())[:8],
            side=side,
            order_type=OrderType.LIMIT,
            size=size,
            price=price,
            status=OrderStatus.OPEN,
        )
        self.orders[order.order_id] = order
        self._log(f"📝 LIMIT: {side.value} {size:.6f} @ ${price:.2f}")
        return order
    
    def place_stop_order(self, side: OrderSide, size: float,
                         stop_price: float) -> SimulatedOrder:
        """Place a stop order (for stop-loss)."""
        order = SimulatedOrder(
            order_id=str(uuid.uuid4())[:8],
            side=side,
            order_type=OrderType.STOP,
            size=size,
            stop_price=stop_price,
            status=OrderStatus.OPEN,
        )
        self.orders[order.order_id] = order
        self._log(f"🛑 STOP: {side.value} {size:.6f} @ ${stop_price:.2f}")
        return order
    
    def place_stop_limit_order(self, side: OrderSide, size: float,
                               stop_price: float, limit_price: float) -> SimulatedOrder:
        """Place a stop-limit order."""
        order = SimulatedOrder(
            order_id=str(uuid.uuid4())[:8],
            side=side,
            order_type=OrderType.STOP_LIMIT,
            size=size,
            stop_price=stop_price,
            price=limit_price,
            status=OrderStatus.OPEN,
        )
        self.orders[order.order_id] = order
        self._log(f"🛑 STOP-LIMIT: {side.value} {size:.6f} stop@${stop_price:.2f} limit@${limit_price:.2f}")
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status in (OrderStatus.PENDING, OrderStatus.OPEN):
                order.status = OrderStatus.CANCELLED
                del self.orders[order_id]
                self._log(f"❌ Cancelled order {order_id}")
                return True
        return False
    
    def get_order(self, order_id: str) -> Optional[SimulatedOrder]:
        """Get order by ID."""
        if order_id in self.orders:
            return self.orders[order_id]
        # Check filled orders
        for order in self.filled_orders:
            if order.order_id == order_id:
                return order
        return None
    
    def get_open_orders(self) -> List[SimulatedOrder]:
        """Get all open orders."""
        return [o for o in self.orders.values() 
                if o.status in (OrderStatus.PENDING, OrderStatus.OPEN)]
    
    def get_portfolio_value(self, price: Optional[float] = None) -> float:
        """Get total portfolio value in USD."""
        p = price or self._current_price
        return self._currency + (self._asset * p)
    
    def get_state(self) -> dict:
        """Get current interface state for dashboard."""
        return {
            'currency': self._currency,
            'asset': self._asset,
            'current_price': self._current_price,
            'portfolio_value': self.get_portfolio_value(),
            'open_orders': [o.to_dict() for o in self.get_open_orders()],
            'trade_count': len(self.filled_orders),
        }
    
    def reset(self):
        """Reset to initial state."""
        self._currency = self._initial_currency
        self._asset = self._initial_asset
        self._current_price = 0.0
        self.orders.clear()
        self.filled_orders.clear()
        self.trade_history.clear()
        self._log("🔄 Interface reset")
