from abc import ABC, abstractmethod
from typing import List, Tuple

class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    All strategies must implement buy_signal() and sell_signal() methods.
    """
    
    def __init__(self, bot):
        """
        Initialize strategy with reference to the bot.
        
        Args:
            bot: The Bot instance that will use this strategy
        """
        self.bot = bot
    
    @abstractmethod
    def buy_signal(self, candles: List[Tuple]) -> bool:
        """
        Determine if conditions are right to buy.
        
        Args:
            candles: List of candle data [(timestamp, low, high, open, close, volume), ...]
        
        Returns:
            bool: True if should buy, False otherwise
        """
        pass
    
    @abstractmethod
    def sell_signal(self, candles: List[Tuple]) -> bool:
        """
        Determine if conditions are right to sell.
        
        Args:
            candles: List of candle data [(timestamp, low, high, open, close, volume), ...]
        
        Returns:
            bool: True if should sell, False otherwise
        """
        pass
    
    def check_baseline_for_buy(self, current_price: float) -> bool:
        """
        Check if buying at current price would exceed asset baseline (with loss tolerance).
        This prevents the bot from signaling trades that will be rejected anyway.
        
        Args:
            current_price: Current asset price
            
        Returns:
            bool: True if trade would be profitable, False otherwise
        """
        if self.bot.position != "short":
            return False
            
        amount_to_spend = self.bot.currency
        amount_expected = (amount_to_spend * (1 - self.bot.fee_rate)) / current_price
        
        # Check with loss tolerance (same logic as bot.execute_buy)
        min_acceptable = self.bot.asset_baseline * (1 - self.bot.loss_tolerance)
        return amount_expected > min_acceptable
    
    def check_baseline_for_sell(self, current_price: float) -> bool:
        """
        Check if selling at current price would exceed currency baseline (with loss tolerance).
        This prevents the bot from signaling trades that will be rejected anyway.
        
        Args:
            current_price: Current asset price
            
        Returns:
            bool: True if trade would be profitable, False otherwise
        """
        if self.bot.position != "long":
            return False
            
        amount_to_sell = self.bot.asset
        amount_expected = (amount_to_sell * current_price) * (1 - self.bot.fee_rate)
        
        # Check with loss tolerance (same logic as bot.execute_sell)
        min_acceptable = self.bot.currency_baseline * (1 - self.bot.loss_tolerance)
        return amount_expected > min_acceptable
    
    def explain(self) -> List[str]:
        """
        Provide a human-readable explanation of the strategy.
        Override this in subclasses to provide strategy-specific details.
        
        Returns:
            List[str]: Lines of explanation text
        """
        return [
            f"Strategy: {self.__class__.__name__}",
            "No detailed explanation available for this strategy."
        ]
