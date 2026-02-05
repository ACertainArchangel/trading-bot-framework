"""
Order manager for bracket orders (entry + stop loss + take profit).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Callable
import time

from .position import Position, PositionSide, ExitReason


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Order:
    """Represents a single order."""
    order_id: str
    side: str  # "BUY" or "SELL"
    order_type: OrderType
    size: float
    price: Optional[float] = None  # For LIMIT orders
    stop_price: Optional[float] = None  # For STOP orders
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_size: float = 0.0
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        self.updated_at = self.created_at


@dataclass
class BracketOrder:
    """
    A bracket order consists of:
    - Entry order (to open position)
    - Stop loss order (to limit downside)
    - Take profit order (to capture gains)
    
    When entry fills, SL and TP orders are placed.
    When either SL or TP fills, the other is cancelled.
    """
    position: Position
    entry_order: Optional[Order] = None
    stop_loss_order: Optional[Order] = None
    take_profit_order: Optional[Order] = None
    
    @property
    def is_complete(self) -> bool:
        """Check if bracket is complete (position closed)."""
        return self.position.exit_reason is not None


class OrderManager:
    """
    Manages bracket orders for aggressive trading.
    
    Responsibilities:
    - Place entry orders with associated SL/TP
    - Monitor order status
    - Cancel orphaned orders when SL or TP fills
    - Track all open positions
    """
    
    def __init__(self, interface, fee_rate: float = 0.0025, 
                 logger: Callable[[str], None] = None):
        """
        Args:
            interface: Trading interface (Coinbase, Paper, etc.)
            fee_rate: Trading fee as decimal (0.0025 = 0.25%)
            logger: Logging function
        """
        self.interface = interface
        self.fee_rate = fee_rate
        self._log = logger or (lambda x: None)
        
        # Track all brackets
        self.brackets: List[BracketOrder] = []
        self.closed_brackets: List[BracketOrder] = []
        
        # Order ID counter for paper trading
        self._order_counter = 0
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"ORD_{int(time.time())}_{self._order_counter}"
    
    def open_bracket(self, side: PositionSide, size: float, entry_price: float,
                     stop_loss_pct: float = 0.02, take_profit_pct: float = 0.05,
                     trailing_stop: bool = False, order_type: OrderType = OrderType.LIMIT
                     ) -> Optional[BracketOrder]:
        """
        Open a new bracket order (position with SL/TP).
        
        Args:
            side: LONG or SHORT
            size: Position size in asset units
            entry_price: Desired entry price
            stop_loss_pct: Stop loss percentage (0.02 = 2%)
            take_profit_pct: Take profit percentage (0.05 = 5%)
            trailing_stop: Use trailing stop instead of fixed
            order_type: MARKET or LIMIT for entry
            
        Returns:
            BracketOrder if entry placed successfully, None otherwise
        """
        # Create position
        position = Position(
            side=side,
            entry_price=entry_price,
            size=size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=stop_loss_pct if trailing_stop else None,
        )
        
        # Create entry order
        entry_side = "BUY" if side == PositionSide.LONG else "SELL"
        entry_order = Order(
            order_id=self._generate_order_id(),
            side=entry_side,
            order_type=order_type,
            size=size,
            price=entry_price if order_type == OrderType.LIMIT else None,
        )
        
        # Place entry order
        try:
            if order_type == OrderType.MARKET:
                # Market order - immediate fill
                result = self._place_market_order(entry_side, size)
            else:
                # Limit order
                result = self._place_limit_order(entry_side, size, entry_price)
            
            if result:
                entry_order.order_id = result.get("order_id", entry_order.order_id)
                entry_order.status = OrderStatus.OPEN
                position.entry_order_id = entry_order.order_id
                
                self._log(f"📤 Entry order placed: {entry_side} {size:.6f} @ ${entry_price:.2f}")
            else:
                self._log(f"❌ Failed to place entry order")
                return None
                
        except Exception as e:
            self._log(f"❌ Entry order error: {e}")
            return None
        
        # Create bracket
        bracket = BracketOrder(
            position=position,
            entry_order=entry_order,
        )
        
        self.brackets.append(bracket)
        return bracket
    
    def _place_market_order(self, side: str, size: float) -> Optional[Dict]:
        """Place a market order through the interface."""
        # This will be implemented based on the actual interface
        # For now, return a mock result
        return {"order_id": self._generate_order_id(), "status": "filled"}
    
    def _place_limit_order(self, side: str, size: float, price: float) -> Optional[Dict]:
        """Place a limit order through the interface."""
        # This will be implemented based on the actual interface
        return {"order_id": self._generate_order_id(), "status": "open"}
    
    def _place_stop_order(self, side: str, size: float, stop_price: float) -> Optional[Dict]:
        """Place a stop order through the interface."""
        return {"order_id": self._generate_order_id(), "status": "open"}
    
    def _cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        # This will be implemented based on the actual interface
        return True
    
    def update(self, current_price: float):
        """
        Update all brackets with current price.
        Check for fills, trigger SL/TP, etc.
        
        Args:
            current_price: Current market price
        """
        for bracket in self.brackets[:]:  # Copy list to allow modification
            if bracket.is_complete:
                continue
            
            position = bracket.position
            
            # Check if entry filled (for backtest/paper trading)
            if not position.is_filled and bracket.entry_order:
                if self._check_entry_fill(bracket, current_price):
                    self._on_entry_filled(bracket, current_price)
            
            # Check SL/TP if position is open
            if position.is_filled:
                exit_reason = position.update_price(current_price)
                if exit_reason:
                    self._close_bracket(bracket, current_price, exit_reason)
    
    def _check_entry_fill(self, bracket: BracketOrder, price: float) -> bool:
        """Check if entry order would fill at current price."""
        entry = bracket.entry_order
        if not entry or entry.status != OrderStatus.OPEN:
            return False
        
        if entry.order_type == OrderType.MARKET:
            return True
        
        if entry.order_type == OrderType.LIMIT:
            if entry.side == "BUY" and price <= entry.price:
                return True
            if entry.side == "SELL" and price >= entry.price:
                return True
        
        return False
    
    def _on_entry_filled(self, bracket: BracketOrder, fill_price: float):
        """Handle entry order fill."""
        position = bracket.position
        entry = bracket.entry_order
        
        entry.status = OrderStatus.FILLED
        entry.filled_price = fill_price
        entry.filled_size = entry.size
        entry.updated_at = datetime.utcnow()
        
        position.is_filled = True
        position.entry_price = fill_price  # Update to actual fill price
        
        # Recalculate SL/TP based on actual fill price
        if position.stop_loss_pct:
            if position.side == PositionSide.LONG:
                position.stop_loss_price = fill_price * (1 - position.stop_loss_pct)
            else:
                position.stop_loss_price = fill_price * (1 + position.stop_loss_pct)
        
        if position.take_profit_pct:
            if position.side == PositionSide.LONG:
                position.take_profit_price = fill_price * (1 + position.take_profit_pct)
            else:
                position.take_profit_price = fill_price * (1 - position.take_profit_pct)
        
        self._log(f"✅ Entry filled: {entry.side} {entry.size:.6f} @ ${fill_price:.2f}")
        self._log(f"   SL: ${position.stop_loss_price:.2f} | TP: ${position.take_profit_price:.2f}")
        
        # Place SL/TP orders (for live trading)
        self._place_sl_tp_orders(bracket)
    
    def _place_sl_tp_orders(self, bracket: BracketOrder):
        """Place stop loss and take profit orders after entry fills."""
        position = bracket.position
        
        # Determine exit side (opposite of entry)
        exit_side = "SELL" if position.side == PositionSide.LONG else "BUY"
        
        # Stop loss order
        if position.stop_loss_price:
            sl_order = Order(
                order_id=self._generate_order_id(),
                side=exit_side,
                order_type=OrderType.STOP,
                size=position.size,
                stop_price=position.stop_loss_price,
                status=OrderStatus.OPEN,
            )
            bracket.stop_loss_order = sl_order
            position.stop_loss_order_id = sl_order.order_id
        
        # Take profit order
        if position.take_profit_price:
            tp_order = Order(
                order_id=self._generate_order_id(),
                side=exit_side,
                order_type=OrderType.LIMIT,
                size=position.size,
                price=position.take_profit_price,
                status=OrderStatus.OPEN,
            )
            bracket.take_profit_order = tp_order
            position.take_profit_order_id = tp_order.order_id
    
    def _close_bracket(self, bracket: BracketOrder, exit_price: float, reason: ExitReason):
        """Close a bracket order."""
        position = bracket.position
        position.close(exit_price, reason)
        
        # Cancel the other order
        if reason in [ExitReason.STOP_LOSS, ExitReason.TRAILING_STOP]:
            if bracket.take_profit_order:
                bracket.take_profit_order.status = OrderStatus.CANCELLED
                self._cancel_order(bracket.take_profit_order.order_id)
        elif reason == ExitReason.TAKE_PROFIT:
            if bracket.stop_loss_order:
                bracket.stop_loss_order.status = OrderStatus.CANCELLED
                self._cancel_order(bracket.stop_loss_order.order_id)
        
        # Calculate P&L
        if position.side == PositionSide.LONG:
            pnl = (exit_price - position.entry_price) * position.size
        else:
            pnl = (position.entry_price - exit_price) * position.size
        
        # Subtract fees (entry + exit)
        entry_fee = position.entry_price * position.size * self.fee_rate
        exit_fee = exit_price * position.size * self.fee_rate
        net_pnl = pnl - entry_fee - exit_fee
        
        emoji = "🟢" if net_pnl > 0 else "🔴"
        self._log(f"{emoji} Position closed: {reason.value}")
        self._log(f"   Entry: ${position.entry_price:.2f} → Exit: ${exit_price:.2f}")
        self._log(f"   Gross P&L: ${pnl:.4f} | Net: ${net_pnl:.4f}")
        
        # Move to closed
        self.brackets.remove(bracket)
        self.closed_brackets.append(bracket)
    
    def close_all(self, current_price: float, reason: ExitReason = ExitReason.MANUAL):
        """Close all open positions."""
        for bracket in self.brackets[:]:
            if bracket.position.is_filled:
                self._close_bracket(bracket, current_price, reason)
    
    @property
    def open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [b.position for b in self.brackets if b.position.is_filled]
    
    @property
    def pending_entries(self) -> List[BracketOrder]:
        """Get brackets with pending entry orders."""
        return [b for b in self.brackets if not b.position.is_filled]
    
    def get_stats(self) -> Dict:
        """Get trading statistics."""
        total_trades = len(self.closed_brackets)
        if total_trades == 0:
            return {"total_trades": 0}
        
        wins = 0
        losses = 0
        total_pnl = 0.0
        sl_exits = 0
        tp_exits = 0
        
        for bracket in self.closed_brackets:
            pos = bracket.position
            if pos.exit_price and pos.entry_price:
                if pos.side == PositionSide.LONG:
                    pnl = (pos.exit_price - pos.entry_price) * pos.size
                else:
                    pnl = (pos.entry_price - pos.exit_price) * pos.size
                
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
                
                if pos.exit_reason in [ExitReason.STOP_LOSS, ExitReason.TRAILING_STOP]:
                    sl_exits += 1
                elif pos.exit_reason == ExitReason.TAKE_PROFIT:
                    tp_exits += 1
        
        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total_trades if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / total_trades,
            "stop_loss_exits": sl_exits,
            "take_profit_exits": tp_exits,
        }
