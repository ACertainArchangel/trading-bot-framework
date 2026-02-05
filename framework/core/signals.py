"""
Trading Signals - Communication between strategies and execution.

Signals tell the bot what action to take: buy, sell, or hold.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class SignalStrength(Enum):
    """How confident is the signal?"""
    WEAK = 1
    MODERATE = 2
    STRONG = 3


class Signal(Enum):
    """
    Simple trading signal.
    
    Used by basic strategies that just indicate buy/sell/hold.
    """
    HOLD = auto()
    BUY = auto()
    SELL = auto()


@dataclass
class EntrySignal:
    """
    Rich entry signal with risk management parameters.
    
    Use this when you want to specify stop-loss, take-profit, or position sizing.
    Strategies can return either a bool (simple) or EntrySignal (advanced).
    
    Attributes:
        side: 'buy' or 'sell'
        strength: Signal confidence level
        stop_loss_pct: Stop-loss as percentage from entry (e.g., 0.02 = 2%)
        take_profit_pct: Take-profit as percentage from entry (e.g., 0.05 = 5%)
        use_trailing_stop: Whether to use a trailing stop instead of fixed
        size_pct: Position size as fraction of available capital (0.0 - 1.0)
        limit_price: For limit orders, None = market order
        reason: Human-readable explanation for logging
    
    Example:
        >>> signal = EntrySignal(
        ...     side='buy',
        ...     stop_loss_pct=0.02,
        ...     take_profit_pct=0.04,
        ...     reason="MACD crossover with RSI confirmation"
        ... )
    """
    side: str  # 'buy' or 'sell'
    strength: SignalStrength = SignalStrength.MODERATE
    
    # Risk management
    stop_loss_pct: float = 0.02  # 2% default
    take_profit_pct: float = 0.05  # 5% default
    use_trailing_stop: bool = False
    
    # Position sizing (fraction of available capital)
    size_pct: float = 1.0
    
    # Order type
    limit_price: Optional[float] = None  # None = market order
    
    # Logging
    reason: str = ""
    
    def __post_init__(self):
        """Validate signal parameters."""
        if self.side not in ('buy', 'sell'):
            raise ValueError(f"side must be 'buy' or 'sell', got '{self.side}'")
        if not 0 < self.stop_loss_pct < 1:
            raise ValueError(f"stop_loss_pct must be between 0 and 1, got {self.stop_loss_pct}")
        if not 0 < self.take_profit_pct < 1:
            raise ValueError(f"take_profit_pct must be between 0 and 1, got {self.take_profit_pct}")
        if not 0 < self.size_pct <= 1:
            raise ValueError(f"size_pct must be between 0 and 1, got {self.size_pct}")
    
    @property
    def is_buy(self) -> bool:
        return self.side == 'buy'
    
    @property
    def is_sell(self) -> bool:
        return self.side == 'sell'
