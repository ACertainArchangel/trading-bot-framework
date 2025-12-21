"""
Greedy Momentum Trading Strategy

This is a variation of the momentum strategy that becomes "greedy" after periods
of inactivity. If no trade has occurred for a full day (288 candles at 5-minute 
intervals), the strategy will take profit early on the next favorable opportunity.

Trading Logic:
- Normal momentum signals: Buy on strong upward momentum, sell on strong downward momentum
- Greedy mode (after 1 day of no trades):
  - If holding USD: Buy when price crosses slightly above break-even (profit_margin above last sell)
  - If holding BTC: Sell when price crosses slightly above break-even (profit_margin above last buy)
- The idea: If we've been waiting a long time, take small profits rather than wait for full signals

This helps capture small gains during sideways/ranging markets where full momentum
signals may not trigger.

ECONOMICS-AWARE:
- Strategy now has direct access to fee_rate and loss_tolerance
- Uses would_be_profitable_buy/sell() to check profitability BEFORE signaling
- No more rejected trades - signals are only generated for profitable trades
"""

from typing import List
from .base import Strategy


class GreedyMomentumStrategy(Strategy):
    """
    Greedy Momentum strategy that takes early profits after periods of inactivity.
    
    Combines momentum signals with greedy profit-taking when trades haven't happened
    for a while.
    
    Now economics-aware: checks profitability including fees before signaling.
    """
    
    def __init__(self, bot, period: int = 10, buy_threshold: float = 2.0, 
                 sell_threshold: float = -2.0, profit_margin: float = 0.5,
                 patience_candles: int = 288, fee_rate: float = 0.0,
                 loss_tolerance: float = 0.0):
        """
        Initialize Greedy Momentum strategy.
        
        Args:
            bot: Bot instance
            period: Lookback period for ROC calculation (default 10)
            buy_threshold: ROC % threshold for normal buy signal (default 2.0%)
            sell_threshold: ROC % threshold for normal sell signal (default -2.0%)
            profit_margin: % above break-even to trigger greedy trade (default 0.5%)
            patience_candles: Candles to wait before becoming greedy (default 288 = 1 day at 5min)
            fee_rate: Trading fee rate as decimal (e.g., 0.0025 for 0.25%)
            loss_tolerance: Max acceptable loss as decimal (e.g., 0.0 for no losses)
        """
        super().__init__(bot, fee_rate=fee_rate, loss_tolerance=loss_tolerance)
        self.period = period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.profit_margin = profit_margin
        self.patience_candles = patience_candles
        self.min_candles = period + 1
        
        # Track trading activity
        self.candles_since_last_trade = 0
        self.impatient_candles = 0  # Only count when price is unprofitable
        self.last_buy_price = None
        self.last_sell_price = None
        
        # Cache for performance (avoid re-extracting prices every candle)
        self._closes_cache = []
        
    def __str__(self):
        return (f"GreedyMomentum({self.period}, buy={self.buy_threshold}%, "
                f"sell={self.sell_threshold}%, margin={self.profit_margin}%, "
                f"patience={self.patience_candles}, fee={self.fee_rate*100:.3f}%)")
    
    def calculate_roc(self, prices: List[float]) -> float:
        """
        Calculate Rate of Change (ROC) as a percentage.
        ROC = ((Current - Old) / Old) * 100
        
        Args:
            prices: List of closing prices
            
        Returns:
            ROC percentage
        """
        if len(prices) < self.period + 1:
            return 0.0
        
        current_price = prices[-1]
        old_price = prices[-(self.period + 1)]
        
        if old_price == 0:
            return 0.0
        
        roc = ((current_price - old_price) / old_price) * 100
        return roc
    
    def is_greedy_mode(self) -> bool:
        """Check if we should be in greedy mode (patient waiting period exceeded)."""
        return self.impatient_candles >= self.patience_candles
    
    def is_price_profitable(self, current_price: float) -> bool:
        """
        Check if current price would allow a profitable trade INCLUDING FEES.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if price is above profitable threshold for current position
        """
        if self.bot.position == "short":
            # Holding USD - check if we can buy and later sell profitably
            # Need: current_price >= last_sell_price * (1 + profit_margin)
            # AND: the trade must beat our baseline after fees
            if self.last_sell_price is None:
                return False
            profitable_buy_price = self.last_sell_price * (1 + self.profit_margin / 100)
            return current_price >= profitable_buy_price
        else:
            # Holding BTC - check if we can sell profitably
            if self.last_buy_price is None:
                return False
            profitable_sell_price = self.last_buy_price * (1 + self.profit_margin / 100)
            return current_price >= profitable_sell_price
    
    def greedy_buy_signal(self, current_price: float) -> bool:
        """
        Greedy buy: If holding USD and been waiting, buy when price crosses slightly
        above where we last sold (indicating we can make a quick profit).
        
        Now checks would_be_profitable_buy() to ensure trade beats baseline after fees.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if greedy buy condition met AND trade would be profitable
        """
        if not self.is_greedy_mode():
            return False
        
        # Only greedy buy if we're holding USD (not already in BTC)
        if self.bot.position == "long":
            return False
        
        # Need to know where we last sold
        if self.last_sell_price is None:
            return False
        
        # Buy if price is profit_margin% above where we sold
        target_price = self.last_sell_price * (1 + self.profit_margin / 100)
        
        if current_price >= target_price:
            # CRITICAL: Check if this trade would be profitable after fees
            return self.would_be_profitable_buy(current_price)
        
        return False
    
    def greedy_sell_signal(self, current_price: float) -> bool:
        """
        Greedy sell: If holding BTC and been waiting, sell when price crosses slightly
        above where we last bought (indicating we can make a quick profit).
        
        Now checks would_be_profitable_sell() to ensure trade beats baseline after fees.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if greedy sell condition met AND trade would be profitable
        """
        if not self.is_greedy_mode():
            return False
        
        # Only greedy sell if we're holding BTC
        if self.bot.position == "short":
            return False
        
        # Need to know where we last bought
        if self.last_buy_price is None:
            return False
        
        # Sell if price is profit_margin% above where we bought
        target_price = self.last_buy_price * (1 + self.profit_margin / 100)
        
        if current_price >= target_price:
            # CRITICAL: Check if this trade would be profitable after fees
            return self.would_be_profitable_sell(current_price)
        
        return False
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal from either normal momentum or greedy logic.
        
        All signals are checked against would_be_profitable_buy() to ensure
        the trade will beat our baseline after accounting for fees.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Update closes cache (only append new prices)
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Check greedy buy first (takes priority when patient)
        # greedy_buy_signal already checks would_be_profitable_buy internally
        if self.greedy_buy_signal(current_price):
            # Reset counters on successful signal
            self.candles_since_last_trade = 0
            self.impatient_candles = 0
            self.last_buy_price = current_price
            return True
        
        # Normal momentum buy signal (use cached closes)
        current_roc = self.calculate_roc(self._closes_cache)
        previous_roc = self.calculate_roc(self._closes_cache[:-1])
        
        # Buy when ROC crosses above buy threshold
        momentum_buy = previous_roc <= self.buy_threshold and current_roc > self.buy_threshold
        
        if momentum_buy:
            # CRITICAL: Check if this trade would be profitable after fees
            if self.would_be_profitable_buy(current_price):
                self.candles_since_last_trade = 0
                self.impatient_candles = 0
                self.last_buy_price = current_price
                return True
        
        # No trade this candle - increment impatience only if price is unprofitable
        self.candles_since_last_trade += 1
        if not self.is_price_profitable(current_price):
            self.impatient_candles += 1
        else:
            # Price is profitable but no signal - reset impatience
            self.impatient_candles = 0
        
        return False
    
    def sell_signal(self, candles: List) -> bool:
        """
        Generate sell signal from either normal momentum or greedy logic.
        
        All signals are checked against would_be_profitable_sell() to ensure
        the trade will beat our baseline after accounting for fees.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles + 1:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Update closes cache (only append new prices)
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Check greedy sell first (takes priority when patient)
        # greedy_sell_signal already checks would_be_profitable_sell internally
        if self.greedy_sell_signal(current_price):
            # Reset counters on successful signal
            self.candles_since_last_trade = 0
            self.impatient_candles = 0
            self.last_sell_price = current_price
            return True
        
        # Normal momentum sell signal (use cached closes)
        current_roc = self.calculate_roc(self._closes_cache)
        previous_roc = self.calculate_roc(self._closes_cache[:-1])
        
        # Sell when ROC crosses below sell threshold
        momentum_sell = previous_roc >= self.sell_threshold and current_roc < self.sell_threshold
        
        if momentum_sell:
            # CRITICAL: Check if this trade would be profitable after fees
            if self.would_be_profitable_sell(current_price):
                self.candles_since_last_trade = 0
                self.impatient_candles = 0
                self.last_sell_price = current_price
                return True
        
        # No trade this candle - increment impatience only if price is unprofitable
        self.candles_since_last_trade += 1
        if not self.is_price_profitable(current_price):
            self.impatient_candles += 1
        else:
            # Price is profitable but no signal - reset impatience
            self.impatient_candles = 0
        
        return False
    
    @property
    def name(self):
        """Return strategy name."""
        return f"Greedy Momentum (ROC {self.period})"
    
    def explain(self) -> List[str]:
        """Provide explanation of the strategy."""
        greedy_status = "🟢 GREEDY MODE" if self.is_greedy_mode() else "⏳ Normal Mode"
        candles_left = max(0, self.patience_candles - self.impatient_candles)
        
        lines = [
            f"⚡💰 Greedy Momentum Strategy (ROC {self.period}-period)",
            f"   • Normal: Buy on {self.buy_threshold}% momentum, Sell on {self.sell_threshold}%",
            f"   • Greedy: After {self.patience_candles} unprofitable candles ({self.patience_candles * 5 // 60}h @ 5min), take {self.profit_margin}% profit",
            f"   • Fee Rate: {self.fee_rate*100:.4f}%",
            f"   • Loss Tolerance: {self.loss_tolerance*100:.2f}%",
            f"   • Status: {greedy_status} ({candles_left} unprofitable candles until greedy)",
            f"   • Candles since last trade: {self.candles_since_last_trade}",
            f"   • Impatient candles (unprofitable): {self.impatient_candles}"
        ]
        
        if self.last_buy_price:
            lines.append(f"   • Last buy: ${self.last_buy_price:,.2f}")
            if self.is_greedy_mode() and self.bot.position == "long":
                target = self.last_buy_price * (1 + self.profit_margin / 100)
                lines.append(f"   • Greedy sell target: ${target:,.2f}")
        
        if self.last_sell_price:
            lines.append(f"   • Last sell: ${self.last_sell_price:,.2f}")
            if self.is_greedy_mode() and self.bot.position == "short":
                target = self.last_sell_price * (1 + self.profit_margin / 100)
                lines.append(f"   • Greedy buy target: ${target:,.2f}")
        
        # Show min profitable prices
        if self.bot.position == "long":
            min_sell = self.get_min_profitable_sell_price()
            lines.append(f"   • Min profitable sell: ${min_sell:,.2f}")
        else:
            max_buy = self.get_min_profitable_buy_price()
            lines.append(f"   • Max profitable buy: ${max_buy:,.2f}")
        
        return lines
