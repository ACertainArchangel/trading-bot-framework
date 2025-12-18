from abc import ABC, abstractmethod
from typing import List, Tuple

class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    All strategies must implement buy_signal() and sell_signal() methods.
    
    Performance Tracking (Dual Baseline System):
    --------------------------------------------
    The bot tracks performance using TWO independent baselines:
    
    1. USD Baseline (currency_baseline):
       - Tracks the USD value that would result from perfect buy-low/sell-high trading
       - Updated on EVERY trade regardless of position
       - Used to calculate USD APY
    
    2. BTC Baseline (asset_baseline):
       - Tracks the BTC amount that would result from perfect trading
       - Updated on EVERY trade regardless of position
       - Used to calculate BTC APY
    
    APY Calculation:
    ----------------
    - APY is calculated using BASELINES, not raw balances (currency/asset)
    - USD APY = ((currency_baseline / initial_usd_baseline)^(1/years) - 1) * 100
    - BTC APY = ((asset_baseline / initial_crypto_baseline)^(1/years) - 1) * 100
    - This reflects trading performance independent of market movement
    - Both baselines are tracked from bot start and updated on every trade
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
        
        Note: Uses asset_baseline (BTC baseline), not raw asset balance.
        The baseline represents the target BTC amount from optimal trading.
        
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
        
        Note: Uses currency_baseline (USD baseline), not raw currency balance.
        The baseline represents the target USD amount from optimal trading.
        
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
