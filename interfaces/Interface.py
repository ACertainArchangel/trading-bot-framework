from typing import Dict

class Interface:
    # Dust threshold - amounts below this are considered zero (too small to trade)
    DUST_THRESHOLD_USD = 0.10  # $0.10 USD
    DUST_THRESHOLD_ASSET = 0.01  # Generic asset threshold (can be overridden per-asset)
    
    def __init__(self):
        # Interfaces should initialize these in their __init__:
        # self.currency = 0.0
        # self.asset = 0.0
        # self.position = "short" or "long"
        pass

    def _is_dust(self, amount: float, is_currency: bool = True) -> bool:
        """Check if an amount is dust (too small to trade)."""
        threshold = self.DUST_THRESHOLD_USD if is_currency else self.DUST_THRESHOLD_ASSET
        return abs(amount) < threshold

    def validate_position(self):
        """
        Validate that position is clearly defined.
        Must have EITHER currency OR asset, not both or neither.
        Dust amounts (below threshold) are ignored.
        
        Special case: If both are dust, we pick the relatively larger one
        to determine position (the one closest to its dust threshold).
        """
        currency_is_dust = self._is_dust(self.currency, is_currency=True)
        asset_is_dust = self._is_dust(self.asset, is_currency=False)
        
        # Special case: Both are dust - pick the larger relative to threshold
        if currency_is_dust and asset_is_dust:
            if self.currency == 0 and self.asset == 0:
                raise ValueError(
                    "Interface has no balance. Must have either currency > 0 or asset > 0."
                )
            
            # Compare relative sizes (how close to dust threshold)
            currency_ratio = self.currency / self.DUST_THRESHOLD_USD if self.DUST_THRESHOLD_USD > 0 else 0
            asset_ratio = self.asset / self.DUST_THRESHOLD_ASSET if self.DUST_THRESHOLD_ASSET > 0 else 0
            
            # Log warning about dust state
            print(f"⚠️  Both balances are dust: ${self.currency:.6f} USD, {self.asset:.8f} asset")
            print(f"    Treating as {'SHORT (USD)' if currency_ratio >= asset_ratio else 'LONG (asset)'} based on relative size")
            
            # Treat the larger relative amount as the "real" position
            if currency_ratio >= asset_ratio:
                # Treat as SHORT (currency holder)
                if self.position != "short":
                    self.position = "short"
                return  # Skip further validation
            else:
                # Treat as LONG (asset holder)
                if self.position != "long":
                    self.position = "long"
                return  # Skip further validation
        
        # Normal case: Apply dust thresholds
        effective_currency = 0.0 if currency_is_dust else self.currency
        effective_asset = 0.0 if asset_is_dust else self.asset
        
        if effective_asset > 0 and effective_currency > 0:
            raise ValueError(
                f"Interface has both currency ({self.currency}) and asset ({self.asset}). "
                "Must have EITHER currency (SHORT) OR asset (LONG), not both."
            )
        if effective_asset == 0 and effective_currency == 0:
            raise ValueError(
                f"Interface has no significant balance. Currency: {self.currency}, Asset: {self.asset}. "
                f"(Dust thresholds: ${self.DUST_THRESHOLD_USD} USD, {self.DUST_THRESHOLD_ASSET} asset)"
            )
        
        # Verify position matches balances (using effective amounts)
        if effective_asset > 0 and self.position != "long":
            raise ValueError(
                f"Interface has asset ({self.asset}) but position is '{self.position}'. "
                "Position should be 'long' when holding asset."
            )
        if effective_currency > 0 and self.position != "short":
            raise ValueError(
                f"Interface has currency ({self.currency}) but position is '{self.position}'. "
                "Position should be 'short' when holding currency."
            )

    def assert_exchange_sync(self, bot):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def connect_to_exchange(self):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def fetch_exchange_balance_currency(self) -> Dict[str, float]:
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def fetch_exchange_balance_asset(self) -> Dict[str, float]:
        raise NotImplementedError("This method should be implemented by subclasses.")