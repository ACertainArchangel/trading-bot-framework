"""
TradingInterface - Abstract base class for all trading interfaces.

An interface represents a connection to an exchange (real or simulated)
and handles order execution, balance tracking, and position management.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional, Dict, TypedDict


class Allocation(TypedDict, total=False):
    """Position allocation configuration.
    
    Values represent position size as a multiple of capital:
    - Positive: long position
    - Negative: short position
    - 0: no position in that direction
    
    Examples:
        {'short': 0, 'long': 1}     # Standard spot trading (default)
        {'short': -1, 'long': 1}    # Spot with shorting
        {'short': -6, 'long': 6}    # 6x leverage perpetuals
        {'short': 0, 'long': 2}     # 2x long leverage only
    """
    short: float
    long: float


DEFAULT_ALLOCATION: Allocation = {'short': 0, 'long': 1}


class TradingInterface(ABC):
    """
    Abstract base class for trading interfaces.
    
    All interfaces must track:
    - currency: Amount of quote currency (e.g., USD)
    - asset: Amount of base asset (e.g., BTC)
    - position: 'long' (holding asset) or 'short' (holding currency)
    
    Dust Handling:
    Small amounts below the dust threshold are treated as zero.
    This prevents issues with tiny leftover balances after trades.
    """
    
    # Dust thresholds - amounts below these are considered zero
    DUST_USD = 0.10
    DUST_ASSET = 0.0001
    
    def __init__(self, allocation: Optional[Allocation] = None):
        self.currency: float = 0.0
        self.asset: float = 0.0
        self.position: str = "short"
        self._allocation = allocation or DEFAULT_ALLOCATION.copy()
    
    @property
    def allocation(self) -> Allocation:
        """Get current allocation settings."""
        return self._allocation
    
    @allocation.setter
    def allocation(self, value: Allocation):
        """Set allocation with validation."""
        self._validate_allocation(value)
        self._allocation = value
    
    def _validate_allocation(self, alloc: Allocation):
        """Validate allocation values. Override in subclasses for restrictions."""
        if 'long' not in alloc or 'short' not in alloc:
            raise ValueError("Allocation must have 'long' and 'short' keys")
        if alloc['long'] < 0:
            raise ValueError("Long allocation must be >= 0")
        if alloc['short'] > 0:
            raise ValueError("Short allocation must be <= 0")
    
    def get_buy_amount(self, available_currency: float) -> float:
        """Get the amount to spend on a buy based on allocation."""
        return available_currency * abs(self._allocation.get('long', 1))
    
    def get_sell_amount(self, available_asset: float) -> float:
        """Get the amount to sell based on allocation."""
        return available_asset * abs(self._allocation.get('long', 1))
    
    def can_short(self) -> bool:
        """Check if shorting is enabled."""
        return self._allocation.get('short', 0) < 0
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the exchange and sync balances.
        
        Returns:
            True if connected successfully
        """
        pass
    
    @abstractmethod
    def execute_buy(
        self,
        price: float,
        fee_rate: float,
        amount: float
    ) -> Tuple[float, float]:
        """
        Execute a buy order.
        
        Args:
            price: Price to buy at
            fee_rate: Fee rate (as decimal)
            amount: USD amount to spend
        
        Returns:
            (asset_received, currency_spent)
        """
        pass
    
    @abstractmethod
    def execute_sell(
        self,
        price: float,
        fee_rate: float,
        amount: float
    ) -> Tuple[float, float]:
        """
        Execute a sell order.
        
        Args:
            price: Price to sell at
            fee_rate: Fee rate (as decimal)
            amount: Asset amount to sell
        
        Returns:
            (currency_received, asset_spent)
        """
        pass
    
    @abstractmethod
    def get_balance(self, asset: str) -> float:
        """Get balance of specific asset."""
        pass
    
    def is_dust(self, amount: float, is_currency: bool = True) -> bool:
        """Check if amount is below dust threshold."""
        threshold = self.DUST_USD if is_currency else self.DUST_ASSET
        return abs(amount) < threshold
    
    def validate_position(self):
        """
        Validate that position is clearly defined.
        
        Must have EITHER currency OR asset (not both, not neither).
        Dust amounts are ignored.
        """
        has_currency = not self.is_dust(self.currency, True)
        has_asset = not self.is_dust(self.asset, False)
        
        if has_currency and has_asset:
            raise ValueError(
                f"Invalid state: has both currency (${self.currency:.2f}) "
                f"and asset ({self.asset:.8f})"
            )
        
        if not has_currency and not has_asset:
            raise ValueError("Invalid state: no balance")
        
        expected_position = "long" if has_asset else "short"
        if self.position != expected_position:
            raise ValueError(
                f"Position mismatch: have {self.position}, "
                f"should be {expected_position}"
            )
    
    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"currency=${self.currency:.2f}, "
            f"asset={self.asset:.8f}, "
            f"position={self.position})"
        )
