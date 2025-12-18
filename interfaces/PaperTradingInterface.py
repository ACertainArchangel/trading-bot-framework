from typing import Dict, Tuple
from .Interface import Interface

class PaperTradingInterface(Interface):
    def __init__(self, starting_currency: float = 0.0, starting_asset: float = 0.0):
        """
        Initialize paper trading interface with starting balances.
        
        Args:
            starting_currency: Initial USD balance (for SHORT position)
            starting_asset: Initial crypto balance (for LONG position)
            
        Note: Must start with EITHER currency OR asset, not both or neither.
        """
        super().__init__()
        self.trade_log = []
        
        # Validate position clarity
        if starting_currency > 0 and starting_asset > 0:
            raise ValueError(
                "PaperTradingInterface must start with EITHER currency OR asset, not both. "
                "If you want to trade with both, create two separate bots."
            )
        if starting_currency == 0 and starting_asset == 0:
            raise ValueError(
                "PaperTradingInterface must start with some balance. "
                "Provide either starting_currency > 0 or starting_asset > 0."
            )
        
        # Set balances and position
        self.currency = float(starting_currency)
        self.asset = float(starting_asset)
        self.position = "long" if self.asset > 0 else "short"

    def __str__(self):
        return f"PaperTradingInterface(currency={self.currency:.2f}, asset={self.asset:.8f}, position={self.position}, trades={len(self.trade_log)})"

    def assert_exchange_sync(self, bot):
        """For paper trading, always in sync since there's no external exchange"""
        pass

    def connect_to_exchange(self):
        """No connection needed for paper trading"""
        pass

    def fetch_exchange_balance_currency(self) -> Dict[str, float]:
        """Returns simulated currency balance"""
        return {
            "balance": self.currency,
            "available": self.currency,
            "hold": 0.0
        }

    def fetch_exchange_balance_asset(self) -> Dict[str, float]:
        """Returns simulated asset balance"""
        return {
            "balance": self.asset,
            "available": self.asset,
            "hold": 0.0
        }

    def execute_buy(self, price: float, fee_rate: float, currency: float) -> Tuple[float, float]:
        """
        Simulates buying asset with all available currency.
        Returns (amount_received, amount_spent)
        """
        amount_to_spend = currency
        amount_received = (amount_to_spend * (1 - fee_rate)) / price
        
        self.trade_log.append({
            "type": "BUY",
            "price": price,
            "spent": amount_to_spend,
            "received": amount_received,
            "fee_rate": fee_rate
        })
        
        return (amount_received, amount_to_spend)

    def execute_sell(self, price: float, fee_rate: float, asset: float) -> Tuple[float, float]:
        """
        Simulates selling all available asset for currency.
        Returns (amount_received, amount_spent)
        """
        amount_to_spend = asset
        amount_received = (amount_to_spend * price) * (1 - fee_rate)
        
        self.trade_log.append({
            "type": "SELL",
            "price": price,
            "spent": amount_to_spend,
            "received": amount_received,
            "fee_rate": fee_rate
        })
        
        return (amount_received, amount_to_spend)
