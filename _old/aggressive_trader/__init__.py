"""
Aggressive Trader - Trading with stop-loss and take-profit orders.
"""

from .position import Position, PositionSide, ExitReason
from .order_manager import OrderManager, Order, OrderType, OrderStatus, BracketOrder
from .strategies import AggressiveStrategy, EntrySignal, SignalStrength, Candle

__all__ = [
    # Position
    "Position",
    "PositionSide", 
    "ExitReason",
    
    # Orders
    "OrderManager",
    "Order",
    "OrderType",
    "OrderStatus",
    "BracketOrder",
    
    # Strategy
    "AggressiveStrategy",
    "EntrySignal",
    "SignalStrength",
    "Candle",
]
