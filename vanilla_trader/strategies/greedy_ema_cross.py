"""
Greedy EMA Cross Trading Strategy

This is a variation of the EMA crossover strategy that becomes "greedy" after periods
of inactivity. If no trade has occurred after waiting through many unprofitable candles,
the strategy will take profit early on the next favorable opportunity.

Trading Logic:
- Normal EMA signals: Buy on golden cross, sell on death cross
- Greedy mode (after patience_candles of unprofitable prices):
  - If holding USD: Buy when price crosses slightly above break-even (profit_margin above last sell)
  - If holding BTC: Sell when price crosses slightly above break-even (profit_margin above last buy)
- Only counts candles as "impatient" when price is below profitable threshold

This helps capture small gains during sideways markets where EMA crosses may not occur.
"""

from typing import List
from .base import Strategy


class GreedyEMACrossStrategy(Strategy):
    """
    Greedy EMA Cross strategy that takes early profits after periods of unprofitable prices.
    
    Combines EMA crossover signals with greedy profit-taking when prices have been
    unprofitable for extended periods.
    """
    
    def __init__(self, bot, fast: int = 9, slow: int = 21, profit_margin: float = 0.5,
                 patience_candles: int = 288):
        """
        Initialize Greedy EMA Cross strategy.
        
        Args:
            bot: Bot instance
            fast: Fast EMA period (default 9)
            slow: Slow EMA period (default 21)
            profit_margin: % above break-even to trigger greedy trade (default 0.5%)
            patience_candles: Candles to wait before becoming greedy (default 288 = 1 day at 5min)
        """
        super().__init__(bot)
        self.fast = fast
        self.slow = slow
        self.profit_margin = profit_margin
        self.patience_candles = patience_candles
        self.min_candles = slow + 1
        
        # Track trading activity
        self.candles_since_last_trade = 0
        self.impatient_candles = 0  # Only count when price is unprofitable
        self.last_buy_price = None
        self.last_sell_price = None
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return (f"GreedyEMA({self.fast}/{self.slow}, "
                f"margin={self.profit_margin}%, patience={self.patience_candles})")
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average.
        
        Args:
            prices: List of closing prices
            period: EMA period
            
        Returns:
            EMA value
        """
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        
        # Calculate multiplier
        multiplier = 2 / (period + 1)
        
        # Start with SMA for first EMA value
        ema = sum(prices[:period]) / period
        
        # Calculate EMA for remaining prices
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def is_greedy_mode(self) -> bool:
        """Check if we should be in greedy mode (patient waiting period exceeded)."""
        return self.impatient_candles >= self.patience_candles
    
    def is_price_profitable(self, current_price: float) -> bool:
        """
        Check if current price would allow a profitable trade.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if price is above profitable threshold for current position
        """
        if self.bot.position == "short":
            # Holding USD - check if we can buy profitably
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
        
        Args:
            current_price: Current market price
            
        Returns:
            True if greedy buy condition met
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
        
        return current_price >= target_price
    
    def greedy_sell_signal(self, current_price: float) -> bool:
        """
        Greedy sell: If holding BTC and been waiting, sell when price crosses slightly
        above where we last bought (indicating we can make a quick profit).
        
        Args:
            current_price: Current market price
            
        Returns:
            True if greedy sell condition met
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
        
        return current_price >= target_price
    
    def buy_signal(self, candles: List) -> bool:
        """
        Generate buy signal from either normal EMA cross or greedy logic.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Check greedy buy first (takes priority when patient)
        if self.greedy_buy_signal(current_price):
            if self.would_be_profitable_buy(current_price):
                # Reset counters on successful signal
                self.candles_since_last_trade = 0
                self.impatient_candles = 0
                self.last_buy_price = current_price
                return True
        
        # Normal EMA crossover buy signal (use cached closes)
        fast_ema = self.calculate_ema(self._closes_cache, self.fast)
        slow_ema = self.calculate_ema(self._closes_cache, self.slow)
        prev_fast_ema = self.calculate_ema(self._closes_cache[:-1], self.fast)
        prev_slow_ema = self.calculate_ema(self._closes_cache[:-1], self.slow)
        
        # Golden cross: fast EMA crosses above slow EMA
        ema_buy = prev_fast_ema <= prev_slow_ema and fast_ema > slow_ema
        
        if ema_buy:
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
        Generate sell signal from either normal EMA cross or greedy logic.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        # Check greedy sell first (takes priority when patient)
        if self.greedy_sell_signal(current_price):
            if self.would_be_profitable_sell(current_price):
                # Reset counters on successful signal
                self.candles_since_last_trade = 0
                self.impatient_candles = 0
                self.last_sell_price = current_price
                return True
        
        # Normal EMA crossover sell signal (use cached closes)
        fast_ema = self.calculate_ema(self._closes_cache, self.fast)
        slow_ema = self.calculate_ema(self._closes_cache, self.slow)
        prev_fast_ema = self.calculate_ema(self._closes_cache[:-1], self.fast)
        prev_slow_ema = self.calculate_ema(self._closes_cache[:-1], self.slow)
        
        # Death cross: fast EMA crosses below slow EMA
        ema_sell = prev_fast_ema >= prev_slow_ema and fast_ema < slow_ema
        
        if ema_sell:
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
        return f"Greedy EMA Cross ({self.fast}/{self.slow})"
    
    def explain(self) -> List[str]:
        """Provide explanation of the strategy."""
        greedy_status = "🟢 GREEDY MODE" if self.is_greedy_mode() else "⏳ Normal Mode"
        candles_left = max(0, self.patience_candles - self.impatient_candles)
        
        lines = [
            f"🔄💰 Greedy EMA Cross Strategy (EMA {self.fast}/{self.slow})",
            f"   • Normal: Buy on golden cross, Sell on death cross",
            f"   • Greedy: After {self.patience_candles} unprofitable candles ({self.patience_candles * 5 // 60}h @ 5min), take {self.profit_margin}% profit",
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
        
        return lines
