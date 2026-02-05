"""
Strategy - The base class for all trading strategies.

This is the main class that users extend to implement their trading logic.
Strategies receive candlestick data and return buy/sell signals.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Union
from ..core.candle import Candle
from ..core.signals import Signal, EntrySignal


class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    
    To create a strategy, inherit from this class and implement:
    - buy_signal(candles): Return True when you want to buy
    - sell_signal(candles): Return True when you want to sell
    
    Example:
        class MyStrategy(Strategy):
            '''Buy when price drops 2%, sell when it rises 3%.'''
            
            def __init__(self, drop_pct: float = 0.02, rise_pct: float = 0.03):
                super().__init__()
                self.drop_pct = drop_pct
                self.rise_pct = rise_pct
                self.entry_price = None
            
            def buy_signal(self, candles: list[Candle]) -> bool:
                if len(candles) < 2:
                    return False
                pct_change = (candles[-1].close - candles[-2].close) / candles[-2].close
                return pct_change < -self.drop_pct
            
            def sell_signal(self, candles: list[Candle]) -> bool:
                if self.entry_price is None:
                    return False
                pct_gain = (candles[-1].close - self.entry_price) / self.entry_price
                return pct_gain > self.rise_pct
    
    Data Integrity:
    ---------------
    When running with paper_trade() or live_trade(), trades are automatically
    gated behind data validity checks. The framework ensures:
    
    - No gaps exist between candles
    - Data is current (not stale)
    - Trades are paused if data integrity issues are detected
    
    Your strategy doesn't need to check this - the runner handles it.
    However, you can access data validity in advanced scenarios:
    
        # stream.is_data_valid() returns True only if data is complete
    
    Economics-Aware Trading:
    ------------------------
    Strategies have access to trading economics for smarter decision-making:
    
    - self.fee_rate: Fee charged per trade (as decimal, e.g., 0.0025 = 0.25%)
    - self.loss_tolerance: Max acceptable loss (as decimal, e.g., 0.01 = 1%)
    - self.currency_baseline: Target USD value to beat
    - self.asset_baseline: Target asset amount to beat
    
    Use would_be_profitable_buy() and would_be_profitable_sell() to check
    if a trade would be profitable BEFORE signaling:
    
        def buy_signal(self, candles):
            if my_technical_buy_condition(candles):
                return self.would_be_profitable_buy(candles[-1].close)
            return False
    """
    
    # Default allocation: standard spot trading (no shorting, 1x long)
    DEFAULT_ALLOCATION = {'short': 0, 'long': 1}
    
    def __init__(
        self,
        fee_rate: float = 0.0025,
        loss_tolerance: float = 0.0,
        allocation: dict = None,
        **kwargs
    ):
        """
        Initialize the strategy.
        
        Args:
            fee_rate: Trading fee as decimal (0.0025 = 0.25%)
            loss_tolerance: Max loss tolerance as decimal (0.01 = 1%)
            allocation: Position sizing config. Default: {'short': 0, 'long': 1}
                       Examples:
                         {'short': -1, 'long': 1}  # Enable shorting
                         {'short': -3, 'long': 3}  # 3x leverage perps
                       If None, uses DEFAULT_ALLOCATION.
                       Override get_allocation() for dynamic sizing.
            **kwargs: Additional strategy-specific parameters
        
        Note: When used with a Bot, the bot will inject itself and sync
        these values automatically. For backtesting, sensible defaults are used.
        """
        self.fee_rate = fee_rate
        self.loss_tolerance = loss_tolerance
        self._allocation = allocation if allocation is not None else self.DEFAULT_ALLOCATION.copy()
        
        # These are synced from the bot after each trade
        self.currency_baseline = 0.0
        self.asset_baseline = 0.0
        
        # Reference to the bot (set by bot on initialization)
        self._bot = None
    
    @property
    def allocation(self) -> dict:
        """Get the base allocation configuration."""
        return self._allocation
    
    @allocation.setter
    def allocation(self, value: dict):
        """Set the base allocation configuration."""
        self._allocation = value
    
    @staticmethod
    def parse_signal(signal) -> tuple:
        """
        Parse a signal return value into (should_trade, allocation).
        
        Args:
            signal: Return value from buy_signal or sell_signal
        
        Returns:
            (should_trade: bool, allocation: float or None)
            - allocation is None if using default
        """
        if signal is False or signal == 0 or signal == 0.0:
            return (False, None)
        if signal is True:
            return (True, None)
        if isinstance(signal, (int, float)):
            return (True, float(signal))
        # EntrySignal or other truthy value
        return (bool(signal), None)
    
    @property
    def bot(self):
        """Reference to the Bot instance (if attached)."""
        return self._bot
    
    @bot.setter
    def bot(self, value):
        """Set bot reference and sync economics."""
        self._bot = value
        if value is not None:
            self.sync_from_bot()
    
    def sync_from_bot(self):
        """
        Sync economic state from the bot.
        Called automatically after each trade.
        """
        if self._bot is not None:
            self.currency_baseline = getattr(self._bot, 'currency_baseline', 0.0)
            self.asset_baseline = getattr(self._bot, 'asset_baseline', 0.0)
            self.fee_rate = getattr(self._bot, 'fee_rate', self.fee_rate)
            self.loss_tolerance = getattr(self._bot, 'loss_tolerance', self.loss_tolerance)
    
    @abstractmethod
    def buy_signal(self, candles: List[Candle]) -> Union[bool, float, EntrySignal]:
        """
        Determine if conditions are right to buy.
        
        Args:
            candles: Historical candle data, most recent last
        
        Returns:
            bool: True to buy (use default allocation), False to hold
            float: Allocation multiplier (e.g., 1.5 = 150% position, 0.5 = 50%)
                   Return 0 or 0.0 for no signal.
            EntrySignal: Rich signal with stop-loss/take-profit
        
        Example:
            def buy_signal(self, candles):
                if strong_signal:
                    return 1.5  # 150% position for strong signals
                elif weak_signal:
                    return 0.5  # 50% position for weak signals
                return False
        """
        pass
    
    @abstractmethod
    def sell_signal(self, candles: List[Candle]) -> Union[bool, float, EntrySignal]:
        """
        Determine if conditions are right to sell.
        
        Args:
            candles: Historical candle data, most recent last
        
        Returns:
            bool: True to sell (use default allocation), False to hold
            float: Allocation multiplier for short (negative enables short)
                   e.g., -1.0 = 100% short, -2.0 = 2x leveraged short
                   Return 0 or 0.0 for no signal.
            EntrySignal: Rich signal with stop-loss/take-profit
        
        Example:
            def sell_signal(self, candles):
                if strong_bearish:
                    return -1.0  # Go short after selling
                elif take_profit:
                    return True  # Just exit, no short
                return False
        """
        pass
    
    def would_be_profitable_buy(self, price: float, currency: Optional[float] = None) -> bool:
        """
        Check if buying at this price would be profitable after fees.
        
        Uses the asset_baseline (best BTC amount achieved) as the target.
        Accounts for fees and loss_tolerance.
        
        Args:
            price: Price to buy at
            currency: USD amount to spend (uses bot's balance if None)
        
        Returns:
            True if trade would be profitable
        
        Example:
            def buy_signal(self, candles):
                if macd_crossover(candles):
                    return self.would_be_profitable_buy(candles[-1].close)
                return False
        """
        if currency is None:
            if self._bot is None:
                return True  # No bot = trust the signal (backtesting)
            currency = getattr(self._bot, 'currency', 0.0)
        
        if currency <= 0 or price <= 0:
            return False
        
        # Calculate asset received after fees
        asset_after_fees = (currency * (1 - self.fee_rate)) / price
        
        # Must beat baseline minus tolerance
        min_acceptable = self.asset_baseline * (1 - self.loss_tolerance)
        
        return asset_after_fees > min_acceptable
    
    def would_be_profitable_sell(self, price: float, asset: Optional[float] = None) -> bool:
        """
        Check if selling at this price would be profitable after fees.
        
        Uses the currency_baseline (best USD amount achieved) as the target.
        Accounts for fees and loss_tolerance.
        
        Args:
            price: Price to sell at
            asset: Asset amount to sell (uses bot's balance if None)
        
        Returns:
            True if trade would be profitable
        
        Example:
            def sell_signal(self, candles):
                if rsi_overbought(candles):
                    return self.would_be_profitable_sell(candles[-1].close)
                return False
        """
        if asset is None:
            if self._bot is None:
                return True  # No bot = trust the signal (backtesting)
            asset = getattr(self._bot, 'asset', 0.0)
        
        if asset <= 0 or price <= 0:
            return False
        
        # Calculate currency received after fees
        currency_after_fees = (asset * price) * (1 - self.fee_rate)
        
        # Must beat baseline minus tolerance
        min_acceptable = self.currency_baseline * (1 - self.loss_tolerance)
        
        return currency_after_fees > min_acceptable
    
    def get_min_sell_price(self, asset: Optional[float] = None) -> float:
        """
        Calculate the minimum price needed to sell profitably.
        
        Args:
            asset: Asset amount (uses bot's balance if None)
        
        Returns:
            Minimum sell price, or infinity if impossible
        """
        if asset is None:
            if self._bot is None:
                return 0.0
            asset = getattr(self._bot, 'asset', 0.0)
        
        if asset <= 0:
            return float('inf')
        
        min_currency = self.currency_baseline * (1 - self.loss_tolerance)
        return min_currency / (asset * (1 - self.fee_rate))
    
    def get_max_buy_price(self, currency: Optional[float] = None) -> float:
        """
        Calculate the maximum price you can pay to buy profitably.
        
        Args:
            currency: USD amount (uses bot's balance if None)
        
        Returns:
            Maximum buy price, or 0 if impossible
        """
        if currency is None:
            if self._bot is None:
                return float('inf')
            currency = getattr(self._bot, 'currency', 0.0)
        
        if currency <= 0:
            return 0.0
        
        min_asset = self.asset_baseline * (1 - self.loss_tolerance)
        
        if min_asset <= 0:
            return float('inf')  # Any price works
        
        return (currency * (1 - self.fee_rate)) / min_asset
    
    @property
    def name(self) -> str:
        """Strategy name for logging."""
        return self.__class__.__name__
    
    def explain(self) -> List[str]:
        """
        Return a human-readable explanation of this strategy.
        Override in subclasses to provide strategy-specific details.
        
        Returns:
            List of explanation lines
        """
        return [
            f"Strategy: {self.name}",
            f"Fee Rate: {self.fee_rate * 100:.4f}%",
            f"Loss Tolerance: {self.loss_tolerance * 100:.2f}%",
        ]
    
    def __str__(self) -> str:
        return self.name
    
    def __repr__(self) -> str:
        return f"<{self.name} fee={self.fee_rate:.4f} loss_tol={self.loss_tolerance:.4f}>"
