from typing import Dict

class Interface:
    def __init__(self):
        # Interfaces should initialize these in their __init__:
        # self.currency = 0.0
        # self.asset = 0.0
        # self.position = "short" or "long"
        pass

    def validate_position(self):
        """
        Validate that position is clearly defined.
        Must have EITHER currency OR asset, not both or neither.
        """
        if self.asset > 0 and self.currency > 0:
            raise ValueError(
                f"Interface has both currency ({self.currency}) and asset ({self.asset}). "
                "Must have EITHER currency (SHORT) OR asset (LONG), not both."
            )
        if self.asset == 0 and self.currency == 0:
            raise ValueError(
                "Interface has no balance. Must have either currency > 0 or asset > 0."
            )
        
        # Verify position matches balances
        if self.asset > 0 and self.position != "long":
            raise ValueError(
                f"Interface has asset ({self.asset}) but position is '{self.position}'. "
                "Position should be 'long' when holding asset."
            )
        if self.currency > 0 and self.position != "short":
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