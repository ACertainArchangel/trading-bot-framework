"""
Base strategy class for aggressive trading with stop-loss and take-profit.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

from ..position import PositionSide


class SignalStrength(Enum):
    """How confident is the signal?"""
    WEAK = 1
    MODERATE = 2
    STRONG = 3


@dataclass
class EntrySignal:
    """
    Signal to enter a position.
    """
    side: PositionSide  # LONG or SHORT
    strength: SignalStrength = SignalStrength.MODERATE
    
    # Entry configuration
    entry_price: Optional[float] = None  # None = market order
    
    # Risk management
    stop_loss_pct: float = 0.02  # 2% default
    take_profit_pct: float = 0.05  # 5% default
    use_trailing_stop: bool = False
    
    # Position sizing
    size_pct: float = 1.0  # Fraction of available capital (0.0-1.0)
    
    # Reason (for logging/analysis)
    reason: str = ""


@dataclass
class Candle:
    """OHLCV candle data."""
    timestamp: int  # Unix timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class AggressiveStrategy(ABC):
    """
    Base class for aggressive trading strategies.
    
    Unlike vanilla strategies which only signal BUY/SELL,
    aggressive strategies provide full position configuration
    including stop-loss, take-profit, and position sizing.
    """
    
    def __init__(self, bot=None, fee_rate: float = 0.0025):
        """
        Args:
            bot: Reference to the trading bot
            fee_rate: Trading fee as decimal
        """
        self.bot = bot
        self.fee_rate = fee_rate
        
        # Default risk parameters (can be overridden)
        self.default_stop_loss_pct = 0.02  # 2%
        self.default_take_profit_pct = 0.05  # 5%
        self.max_position_size_pct = 0.5  # Max 50% of capital per trade
        self.use_trailing_stop = False
    
    @abstractmethod
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        """
        Determine if we should enter a position.
        
        Args:
            candles: Historical OHLCV data (most recent last)
            current_price: Current market price
            
        Returns:
            EntrySignal if we should enter, None otherwise
        """
        pass
    
    def should_exit_early(self, candles: List[Candle], current_price: float,
                          entry_price: float, side: PositionSide) -> bool:
        """
        Determine if we should exit before SL/TP hit.
        
        Override this for strategies that want custom exit logic
        (e.g., exit on indicator crossover regardless of P&L).
        
        Args:
            candles: Historical OHLCV data
            current_price: Current market price
            entry_price: Position entry price
            side: Position side (LONG/SHORT)
            
        Returns:
            True to exit, False to hold
        """
        return False
    
    def calculate_position_size(self, available_capital: float, 
                                entry_price: float,
                                signal: EntrySignal) -> float:
        """
        Calculate position size based on capital and risk.
        
        Args:
            available_capital: USD available for trading
            entry_price: Expected entry price
            signal: Entry signal with sizing preference
            
        Returns:
            Position size in asset units
        """
        # Apply signal's size preference
        capital_to_use = available_capital * signal.size_pct
        
        # Apply max position size limit
        capital_to_use = min(capital_to_use, available_capital * self.max_position_size_pct)
        
        # Convert to asset units
        size = capital_to_use / entry_price
        
        return size
    
    def get_name(self) -> str:
        """Return strategy name for logging."""
        return self.__class__.__name__


class MomentumStrategy(AggressiveStrategy):
    """
    Example: Simple momentum strategy with configurable SL/TP.
    
    Goes LONG when price is above recent average.
    Goes SHORT when price is below recent average.
    """
    
    def __init__(self, lookback: int = 20, threshold_pct: float = 0.01, **kwargs):
        """
        Args:
            lookback: Number of candles for average
            threshold_pct: % above/below average to trigger
        """
        super().__init__(**kwargs)
        self.lookback = lookback
        self.threshold_pct = threshold_pct
    
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        if len(candles) < self.lookback:
            return None
        
        # Calculate average of recent closes
        recent_closes = [c.close for c in candles[-self.lookback:]]
        avg_price = sum(recent_closes) / len(recent_closes)
        
        deviation = (current_price - avg_price) / avg_price
        
        if deviation > self.threshold_pct:
            # Price above average - momentum up, go LONG
            return EntrySignal(
                side=PositionSide.LONG,
                strength=SignalStrength.MODERATE,
                stop_loss_pct=self.default_stop_loss_pct,
                take_profit_pct=self.default_take_profit_pct,
                use_trailing_stop=self.use_trailing_stop,
                reason=f"Price {deviation*100:.2f}% above {self.lookback}-period avg"
            )
        elif deviation < -self.threshold_pct:
            # Price below average - could go SHORT (if supported)
            # For now, just return None (no shorts)
            pass
        
        return None


class BreakoutStrategy(AggressiveStrategy):
    """
    Example: Breakout strategy.
    
    Goes LONG when price breaks above recent high.
    Uses trailing stop to capture extended moves.
    """
    
    def __init__(self, lookback: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.lookback = lookback
        self.use_trailing_stop = True  # Trailing stop for breakouts
        self.default_stop_loss_pct = 0.015  # Tighter stop
        self.default_take_profit_pct = 0.10  # Larger target
    
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        if len(candles) < self.lookback + 1:
            return None
        
        # Get recent high (excluding current candle)
        recent_highs = [c.high for c in candles[-(self.lookback+1):-1]]
        recent_high = max(recent_highs)
        
        # Check for breakout
        if current_price > recent_high:
            return EntrySignal(
                side=PositionSide.LONG,
                strength=SignalStrength.STRONG,
                stop_loss_pct=self.default_stop_loss_pct,
                take_profit_pct=self.default_take_profit_pct,
                use_trailing_stop=True,
                reason=f"Breakout above {self.lookback}-period high ${recent_high:.2f}"
            )
        
        return None
