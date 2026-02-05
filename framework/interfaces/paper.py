"""
PaperInterface - Simulated trading for backtesting and paper trading.

No real money is used. Perfect for testing strategies.
"""

from typing import Tuple, List, Dict, Optional
from datetime import datetime
from .base import TradingInterface, Allocation, DEFAULT_ALLOCATION


class PaperInterface(TradingInterface):
    """
    Simulated trading interface for backtesting and paper trading.
    
    No real money involved - perfect for testing strategies.
    Supports any allocation including leverage and shorting.
    
    Position Types:
        - "long": Holding the asset (value goes up when price goes up)
        - "short": Holding cash or short position (ready to buy)
    
    Example:
        # Standard spot trading (no shorting)
        interface = PaperInterface(starting_currency=1000)
        
        # With shorting enabled
        interface = PaperInterface(
            starting_currency=1000,
            allocation={'short': -1, 'long': 1}
        )
        
        # 3x leverage perpetuals
        interface = PaperInterface(
            starting_currency=1000,
            allocation={'short': -3, 'long': 3}
        )
    """
    
    def __init__(
        self,
        starting_currency: float = 0.0,
        starting_asset: float = 0.0,
        allocation: Optional[Allocation] = None
    ):
        """
        Initialize paper trading interface.
        
        Args:
            starting_currency: Initial USD balance
            starting_asset: Initial asset balance
            allocation: Position sizing config (default: {'short': 0, 'long': 1})
        
        Note: Provide EITHER currency OR asset, not both.
        """
        super().__init__(allocation=allocation)
        
        if starting_currency > 0 and starting_asset > 0:
            raise ValueError(
                "Start with EITHER currency OR asset, not both. "
                "For portfolio simulation, create multiple bots."
            )
        
        if starting_currency == 0 and starting_asset == 0:
            raise ValueError(
                "Must start with some balance. "
                "Provide starting_currency or starting_asset."
            )
        
        self.currency = float(starting_currency)
        self.asset = float(starting_asset)
        
        # Short position tracking
        self._short_size = 0.0      # Amount of asset shorted
        self._short_entry = 0.0     # Entry price of short
        self._short_collateral = 0.0  # USD collateral locked for short
        
        # Long position tracking (for leverage)
        self._long_entry = 0.0      # Entry price of long
        self._long_leverage = 1.0   # Leverage used
        self._long_collateral = 0.0 # Collateral locked (for leveraged longs)
        
        # Determine initial position
        if self.asset > 0:
            self.position = "long"
        else:
            self.position = "short"  # No asset = short/cash position
        
        self.trade_log: List[Dict] = []
    
    def connect(self) -> bool:
        """No connection needed for paper trading."""
        return True
    
    def execute_buy(
        self,
        price: float,
        fee_rate: float,
        amount: float
    ) -> Tuple[float, float]:
        """
        Simulate buying asset (go long) or closing a short.
        
        Args:
            price: Buy price
            fee_rate: Fee rate (decimal)
            amount: USD to spend
        
        Returns:
            (asset_received, currency_spent)
        """
        # If we're short, this closes the short position
        if self.position == "short" and self._short_size > 0:
            return self._close_short(price, fee_rate)
        
        # Normal long entry with leverage
        leverage = abs(self._allocation.get('long', 1))
        if amount > self.currency:
            amount = self.currency
        
        # Apply leverage to position size
        leveraged_value = amount * leverage
        asset_received = (leveraged_value * (1 - fee_rate)) / price
        
        self.currency -= amount
        self.asset += asset_received
        self._long_entry = price  # Track entry for P&L
        self._long_leverage = leverage
        self.position = "long"
        
        self.trade_log.append({
            'type': 'BUY',
            'timestamp': datetime.utcnow().isoformat(),
            'price': price,
            'spent': amount,
            'received': asset_received,
            'leverage': leverage,
            'fee_rate': fee_rate,
            'fee_paid': leveraged_value * fee_rate
        })
        
        return (asset_received, amount)
    
    def execute_sell(
        self,
        price: float,
        fee_rate: float,
        amount: float
    ) -> Tuple[float, float]:
        """
        Simulate selling asset or opening a short position.
        
        Args:
            price: Sell price
            fee_rate: Fee rate (decimal)
            amount: Asset to sell (or USD value for short entry)
        
        Returns:
            (currency_received, asset_spent)
        """
        # If we have asset (long position), close it
        if self.asset > 0:
            if amount > self.asset:
                amount = self.asset
            
            # Calculate leveraged P&L
            if self._long_leverage > 1:
                # Leveraged position: P&L is magnified
                entry_value = amount * self._long_entry
                exit_value = amount * price
                pnl = (exit_value - entry_value) * self._long_leverage
                # Currency received = original collateral + leveraged P&L - fees
                gross_value = (entry_value / self._long_leverage) + pnl
                fee = abs(exit_value) * fee_rate
                currency_received = gross_value - fee
            else:
                # Standard 1x: simple conversion
                currency_received = (amount * price) * (1 - fee_rate)
            
            self.asset -= amount
            self.currency += currency_received
            
            # Reset leverage tracking
            self._long_entry = 0.0
            self._long_leverage = 1.0
            
            # Go to short position (holding cash, ready to buy)
            self.position = "short"
            
            self.trade_log.append({
                'type': 'SELL',
                'timestamp': datetime.utcnow().isoformat(),
                'price': price,
                'spent': amount,
                'received': currency_received,
                'fee_rate': fee_rate,
                'fee_paid': (amount * price) * fee_rate
            })
            
            # If shorting is enabled, automatically open a short position
            if self.can_short():
                return self._open_short(price, fee_rate)
            
            return (currency_received, amount)
        
        # If we're already short and trying to sell more, try to open leveraged short
        elif self.position == "short" and self._short_size == 0 and self.can_short():
            return self._open_short(price, fee_rate)
        
        return (0.0, 0.0)
    
    def _open_short(self, price: float, fee_rate: float) -> Tuple[float, float]:
        """Open a short position."""
        leverage = abs(self._allocation.get('short', -1))
        
        # Use all available currency as collateral
        collateral = self.currency
        short_value = collateral * leverage
        short_size = short_value / price
        fee = short_value * fee_rate
        
        self._short_size = short_size
        self._short_entry = price
        self._short_collateral = collateral
        self.currency = 0  # Lock collateral
        self.position = "short"
        
        self.trade_log.append({
            'type': 'SHORT',
            'timestamp': datetime.utcnow().isoformat(),
            'price': price,
            'size': short_size,
            'collateral': collateral,
            'leverage': leverage,
            'fee_rate': fee_rate,
            'fee_paid': fee
        })
        
        return (short_value, 0.0)
    
    def _close_short(self, price: float, fee_rate: float) -> Tuple[float, float]:
        """Close a short position and realize P&L."""
        # Calculate P&L: profit when price goes DOWN
        entry_value = self._short_size * self._short_entry
        exit_value = self._short_size * price
        gross_pnl = entry_value - exit_value  # Positive if price dropped
        fee = exit_value * fee_rate
        net_pnl = gross_pnl - fee
        
        # Return collateral + P&L
        returned = self._short_collateral + net_pnl
        
        self.currency = returned
        self._short_size = 0.0
        self._short_entry = 0.0
        self._short_collateral = 0.0
        self.position = "short"  # Back to cash position
        
        self.trade_log.append({
            'type': 'COVER',
            'timestamp': datetime.utcnow().isoformat(),
            'price': price,
            'pnl': net_pnl,
            'returned': returned,
            'fee_rate': fee_rate,
            'fee_paid': fee
        })
        
        return (returned, 0.0)
    
    def get_balance(self, asset: str) -> float:
        """Get balance (simplified - assumes USD or the trading asset)."""
        if asset.upper() in ('USD', 'USDC', 'USDT'):
            return self.currency
        return self.asset
    
    def get_total_value(self, current_price: float) -> float:
        """
        Get total portfolio value in USD.
        
        For leveraged positions, this includes unrealized P&L.
        """
        if self.position == "short" and self._short_size > 0:
            # Short P&L: profit when price goes down
            entry_value = self._short_size * self._short_entry
            current_value = self._short_size * current_price
            unrealized_pnl = entry_value - current_value
            return self._short_collateral + unrealized_pnl
        
        if self.position == "long" and self._long_leverage > 1:
            # Leveraged long P&L
            entry_value = self.asset * self._long_entry
            current_value = self.asset * current_price
            pnl = (current_value - entry_value)  # Already leveraged in asset amount
            # Collateral was (entry_value / leverage)
            collateral = entry_value / self._long_leverage
            return self.currency + collateral + pnl
        
        return self.currency + (self.asset * current_price)
    
    def get_trade_count(self) -> int:
        """Get total number of trades."""
        return len(self.trade_log)
    
    def get_fees_paid(self) -> float:
        """Get total fees paid in USD."""
        return sum(t.get('fee_paid', 0) for t in self.trade_log)
    
    def reset(self, starting_currency: float = 0, starting_asset: float = 0):
        """Reset the interface to starting state."""
        allocation = self._allocation
        self.__init__(starting_currency, starting_asset, allocation)
