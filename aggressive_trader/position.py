"""
Position tracking with stop-loss and take-profit management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PositionSide(Enum):
    LONG = "LONG"    # Bought asset, profit when price goes up
    SHORT = "SHORT"  # Sold asset, profit when price goes down (if supported)
    FLAT = "FLAT"    # No position


class ExitReason(Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    MANUAL = "MANUAL"
    TIMEOUT = "TIMEOUT"


@dataclass
class Position:
    """
    Represents an open trading position with stop-loss and take-profit levels.
    """
    side: PositionSide
    entry_price: float
    size: float  # Amount of asset
    entry_time: datetime = field(default_factory=datetime.utcnow)
    
    # Stop loss configuration
    stop_loss_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None  # As decimal (0.02 = 2%)
    
    # Take profit configuration
    take_profit_price: Optional[float] = None
    take_profit_pct: Optional[float] = None  # As decimal (0.05 = 5%)
    
    # Trailing stop (optional)
    trailing_stop_pct: Optional[float] = None  # As decimal
    highest_price: Optional[float] = None  # For LONG trailing stop
    lowest_price: Optional[float] = None   # For SHORT trailing stop
    
    # Order IDs (for live trading)
    entry_order_id: Optional[str] = None
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    
    # Status
    is_filled: bool = False  # Entry order filled
    exit_reason: Optional[ExitReason] = None
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    
    def __post_init__(self):
        """Calculate SL/TP prices from percentages if not set."""
        if self.side == PositionSide.LONG:
            if self.stop_loss_pct and not self.stop_loss_price:
                self.stop_loss_price = self.entry_price * (1 - self.stop_loss_pct)
            if self.take_profit_pct and not self.take_profit_price:
                self.take_profit_price = self.entry_price * (1 + self.take_profit_pct)
            self.highest_price = self.entry_price
            
        elif self.side == PositionSide.SHORT:
            if self.stop_loss_pct and not self.stop_loss_price:
                self.stop_loss_price = self.entry_price * (1 + self.stop_loss_pct)
            if self.take_profit_pct and not self.take_profit_price:
                self.take_profit_price = self.entry_price * (1 - self.take_profit_pct)
            self.lowest_price = self.entry_price
    
    def update_price(self, current_price: float) -> Optional[ExitReason]:
        """
        Update position with current price. Returns exit reason if SL/TP hit.
        
        Args:
            current_price: Current market price
            
        Returns:
            ExitReason if position should be closed, None otherwise
        """
        if not self.is_filled:
            return None
        
        if self.side == PositionSide.LONG:
            # Update trailing stop
            if self.trailing_stop_pct and current_price > self.highest_price:
                self.highest_price = current_price
                self.stop_loss_price = self.highest_price * (1 - self.trailing_stop_pct)
            
            # Check stop loss
            if self.stop_loss_price and current_price <= self.stop_loss_price:
                return ExitReason.TRAILING_STOP if self.trailing_stop_pct else ExitReason.STOP_LOSS
            
            # Check take profit
            if self.take_profit_price and current_price >= self.take_profit_price:
                return ExitReason.TAKE_PROFIT
                
        elif self.side == PositionSide.SHORT:
            # Update trailing stop
            if self.trailing_stop_pct and current_price < self.lowest_price:
                self.lowest_price = current_price
                self.stop_loss_price = self.lowest_price * (1 + self.trailing_stop_pct)
            
            # Check stop loss
            if self.stop_loss_price and current_price >= self.stop_loss_price:
                return ExitReason.TRAILING_STOP if self.trailing_stop_pct else ExitReason.STOP_LOSS
            
            # Check take profit
            if self.take_profit_price and current_price <= self.take_profit_price:
                return ExitReason.TAKE_PROFIT
        
        return None
    
    def close(self, price: float, reason: ExitReason):
        """Mark position as closed."""
        self.exit_price = price
        self.exit_reason = reason
        self.exit_time = datetime.utcnow()
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L (before fees)."""
        if not self.is_filled or not self.exit_price:
            return 0.0
        
        if self.side == PositionSide.LONG:
            return (self.exit_price - self.entry_price) * self.size
        elif self.side == PositionSide.SHORT:
            return (self.entry_price - self.exit_price) * self.size
        return 0.0
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized P&L as percentage."""
        if not self.is_filled or self.entry_price == 0:
            return 0.0
        
        entry_value = self.entry_price * self.size
        return (self.unrealized_pnl / entry_value) * 100
    
    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio based on SL/TP levels."""
        if not self.stop_loss_price or not self.take_profit_price:
            return None
        
        if self.side == PositionSide.LONG:
            risk = self.entry_price - self.stop_loss_price
            reward = self.take_profit_price - self.entry_price
        else:
            risk = self.stop_loss_price - self.entry_price
            reward = self.entry_price - self.take_profit_price
        
        if risk <= 0:
            return None
        return reward / risk
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "side": self.side.value,
            "entry_price": self.entry_price,
            "size": self.size,
            "entry_time": self.entry_time.isoformat(),
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "trailing_stop_pct": self.trailing_stop_pct,
            "is_filled": self.is_filled,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        """Create from dictionary."""
        pos = cls(
            side=PositionSide(data["side"]),
            entry_price=data["entry_price"],
            size=data["size"],
            stop_loss_price=data.get("stop_loss_price"),
            take_profit_price=data.get("take_profit_price"),
            trailing_stop_pct=data.get("trailing_stop_pct"),
        )
        pos.entry_time = datetime.fromisoformat(data["entry_time"])
        pos.is_filled = data.get("is_filled", False)
        if data.get("exit_reason"):
            pos.exit_reason = ExitReason(data["exit_reason"])
        pos.exit_price = data.get("exit_price")
        if data.get("exit_time"):
            pos.exit_time = datetime.fromisoformat(data["exit_time"])
        return pos
