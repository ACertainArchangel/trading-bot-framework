from abc import ABC, abstractmethod
from typing import List, Tuple

class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    All strategies must implement buy_signal() and sell_signal() methods.
    
    Economics-Aware Trading:
    ------------------------
    Strategies now have direct access to trading economics:
    - fee_rate: The fee charged on each trade (as decimal, e.g., 0.0025 for 0.25%)
    - loss_tolerance: Maximum acceptable loss (as decimal, e.g., 0.0 for no losses)
    - currency_baseline: Target USD value to beat (updated by Bot after trades)
    - asset_baseline: Target BTC amount to beat (updated by Bot after trades)
    
    Strategies should use would_be_profitable_buy() and would_be_profitable_sell()
    to check if a trade would be profitable BEFORE signaling. This prevents
    the Bot from having to reject trades after the fact.
    
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
    
    def __init__(self, bot, fee_rate: float = 0.0, loss_tolerance: float = 0.0):
        """
        Initialize strategy with reference to the bot and trading economics.
        
        Args:
            bot: The Bot instance that will use this strategy
            fee_rate: Trading fee rate as decimal (e.g., 0.0025 for 0.25%)
            loss_tolerance: Max acceptable loss as decimal (e.g., 0.0 for no losses, 0.01 for 1%)
        """
        self.bot = bot
        self.fee_rate = fee_rate
        self.loss_tolerance = loss_tolerance
        
        # Baselines - synced from bot after each trade
        # These represent the targets we need to beat
        self.currency_baseline = 0.0
        self.asset_baseline = 0.0
    
    def sync_from_bot(self):
        """
        Sync baseline values from the bot.
        Called by Bot after initialization and after each trade.
        """
        if self.bot is not None:
            self.currency_baseline = getattr(self.bot, 'currency_baseline', 0.0)
            self.asset_baseline = getattr(self.bot, 'asset_baseline', 0.0)
            # Also sync fee_rate and loss_tolerance if bot has different values
            if hasattr(self.bot, 'fee_rate'):
                self.fee_rate = self.bot.fee_rate
            if hasattr(self.bot, 'loss_tolerance'):
                self.loss_tolerance = self.bot.loss_tolerance
    
    def would_be_profitable_buy(self, price: float, currency_amount: float = None) -> bool:
        """
        Check if buying at the given price would be profitable after fees.
        
        This checks if the BTC we'd receive after fees exceeds our asset_baseline
        (adjusted for loss_tolerance).
        
        Args:
            price: Price to buy at
            currency_amount: USD amount to spend (defaults to bot.currency)
            
        Returns:
            True if trade would be profitable, False otherwise
        """
        if currency_amount is None:
            if self.bot is None:
                return False
            currency_amount = getattr(self.bot, 'currency', 0.0)
        
        if currency_amount <= 0 or price <= 0:
            return False
        
        # Calculate BTC we'd receive after fees
        btc_after_fees = (currency_amount * (1 - self.fee_rate)) / price
        
        # Check against baseline with loss tolerance
        min_acceptable = self.asset_baseline * (1 - self.loss_tolerance)
        
        return btc_after_fees > min_acceptable
    
    def would_be_profitable_sell(self, price: float, asset_amount: float = None) -> bool:
        """
        Check if selling at the given price would be profitable after fees.
        
        This checks if the USD we'd receive after fees exceeds our currency_baseline
        (adjusted for loss_tolerance).
        
        Args:
            price: Price to sell at
            asset_amount: BTC amount to sell (defaults to bot.asset)
            
        Returns:
            True if trade would be profitable, False otherwise
        """
        if asset_amount is None:
            if self.bot is None:
                return False
            asset_amount = getattr(self.bot, 'asset', 0.0)
        
        if asset_amount <= 0 or price <= 0:
            return False
        
        # Calculate USD we'd receive after fees
        usd_after_fees = (asset_amount * price) * (1 - self.fee_rate)
        
        # Check against baseline with loss tolerance
        min_acceptable = self.currency_baseline * (1 - self.loss_tolerance)
        
        return usd_after_fees > min_acceptable
    
    def get_min_profitable_sell_price(self, asset_amount: float = None) -> float:
        """
        Calculate the minimum price needed to sell profitably.
        
        Args:
            asset_amount: BTC amount to sell (defaults to bot.asset)
            
        Returns:
            Minimum price needed, or infinity if no profitable price exists
        """
        if asset_amount is None:
            if self.bot is None:
                return float('inf')
            asset_amount = getattr(self.bot, 'asset', 0.0)
        
        if asset_amount <= 0:
            return float('inf')
        
        min_acceptable_usd = self.currency_baseline * (1 - self.loss_tolerance)
        
        # usd_after_fees = (asset * price) * (1 - fee_rate)
        # min_acceptable = (asset * min_price) * (1 - fee_rate)
        # min_price = min_acceptable / (asset * (1 - fee_rate))
        min_price = min_acceptable_usd / (asset_amount * (1 - self.fee_rate))
        
        return min_price
    
    def get_min_profitable_buy_price(self, currency_amount: float = None) -> float:
        """
        Calculate the maximum price we can pay to buy profitably.
        (Higher price = less BTC received)
        
        Args:
            currency_amount: USD amount to spend (defaults to bot.currency)
            
        Returns:
            Maximum price we can pay, or 0 if no profitable price exists
        """
        if currency_amount is None:
            if self.bot is None:
                return 0.0
            currency_amount = getattr(self.bot, 'currency', 0.0)
        
        if currency_amount <= 0:
            return 0.0
        
        min_acceptable_btc = self.asset_baseline * (1 - self.loss_tolerance)
        
        if min_acceptable_btc <= 0:
            return float('inf')  # Any price works if baseline is 0
        
        # btc_after_fees = (currency * (1 - fee_rate)) / price
        # min_acceptable = (currency * (1 - fee_rate)) / max_price
        # max_price = (currency * (1 - fee_rate)) / min_acceptable
        max_price = (currency_amount * (1 - self.fee_rate)) / min_acceptable_btc
        
        return max_price
    
    @abstractmethod
    def buy_signal(self, candles: List[Tuple]) -> bool:
        """
        Determine if conditions are right to buy.
        
        IMPORTANT: Implementations should call would_be_profitable_buy() 
        before returning True to ensure the trade won't be rejected.
        
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
        
        IMPORTANT: Implementations should call would_be_profitable_sell() 
        before returning True to ensure the trade won't be rejected.
        
        Args:
            candles: List of candle data [(timestamp, low, high, open, close, volume), ...]
        
        Returns:
            bool: True if should sell, False otherwise
        """
        pass
    
    # Keep deprecated methods for backwards compatibility
    def check_baseline_for_buy(self, current_price: float) -> bool:
        """DEPRECATED: Use would_be_profitable_buy() instead."""
        return self.would_be_profitable_buy(current_price)
    
    def check_baseline_for_sell(self, current_price: float) -> bool:
        """DEPRECATED: Use would_be_profitable_sell() instead."""
        return self.would_be_profitable_sell(current_price)
    
    def explain(self) -> List[str]:
        """
        Provide a human-readable explanation of the strategy.
        Override this in subclasses to provide strategy-specific details.
        
        Returns:
            List[str]: Lines of explanation text
        """
        return [
            f"Strategy: {self.__class__.__name__}",
            f"Fee Rate: {self.fee_rate*100:.4f}%",
            f"Loss Tolerance: {self.loss_tolerance*100:.2f}%",
            "No detailed explanation available for this strategy."
        ]
