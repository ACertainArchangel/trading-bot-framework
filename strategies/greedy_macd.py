"""
Greedy MACD Trading Strategy

This is a variation of the MACD strategy that becomes "greedy" after periods
of inactivity. If no trade has occurred for a specified patience period, the 
strategy will take profit early on the next favorable opportunity.

Trading Logic:
- Normal MACD signals: Buy on bullish crossover, sell on bearish crossover
- Greedy mode (after patience_candles of no trades):
  - If holding USD: Buy when price crosses slightly above break-even (profit_margin above last sell)
  - If holding BTC: Sell when price crosses slightly above break-even (profit_margin above last buy)
- The idea: If we've been waiting a long time, take small profits rather than wait for full signals

This helps capture small gains during sideways/ranging markets where full MACD
crossovers may not trigger.
"""

from typing import List, Tuple
from .base import Strategy


class GreedyMACDStrategy(Strategy):
    """
    Greedy MACD strategy that takes early profits after periods of inactivity.
    
    Combines MACD crossover signals with greedy profit-taking when trades haven't 
    happened for a while.
    """
    
    def __init__(self, bot, fast_period: int = 12, slow_period: int = 26, 
                 signal_period: int = 9, profit_margin: float = 0.5,
                 patience_candles: int = 288):
        """
        Initialize Greedy MACD strategy.
        
        Args:
            bot: Bot instance
            fast_period: Period for fast EMA (default 12)
            slow_period: Period for slow EMA (default 26)
            signal_period: Period for signal line EMA (default 9)
            profit_margin: % above break-even to trigger greedy trade (default 0.5%)
            patience_candles: Candles to wait before becoming greedy (default 288 = 1 day at 5min)
        """
        super().__init__(bot)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.profit_margin = profit_margin
        self.patience_candles = patience_candles
        self.min_candles = slow_period + signal_period
        
        # Track trading activity
        self.candles_since_last_trade = 0
        self.impatient_candles = 0  # Only count when price is unprofitable
        self.last_buy_price = None
        self.last_sell_price = None
        
        # Cache for performance
        self._closes_cache = []
        
    def __str__(self):
        return (f"GreedyMACD({self.fast_period}/{self.slow_period}/{self.signal_period}, "
                f"margin={self.profit_margin}%, patience={self.patience_candles})")
    
    def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average.
        
        Args:
            prices: List of closing prices
            period: EMA period
            
        Returns:
            List of EMA values
        """
        if len(prices) < period:
            return []
        
        ema = []
        multiplier = 2 / (period + 1)
        
        # First EMA is SMA
        sma = sum(prices[:period]) / period
        ema.append(sma)
        
        # Calculate rest using EMA formula
        for i in range(period, len(prices)):
            ema_value = (prices[i] - ema[-1]) * multiplier + ema[-1]
            ema.append(ema_value)
        
        return ema
    
    def calculate_macd(self, candles: List[Tuple]) -> Tuple[List[float], List[float], List[float]]:
        """
        Calculate MACD line, signal line, and histogram.
        
        Args:
            candles: List of candle data [(timestamp, low, high, open, close, volume), ...]
            
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        # Update closes cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        if len(self._closes_cache) < self.min_candles:
            return [], [], []
        
        # Calculate EMAs (use cached closes)
        fast_ema = self.calculate_ema(self._closes_cache, self.fast_period)
        slow_ema = self.calculate_ema(self._closes_cache, self.slow_period)
        
        # MACD line = fast EMA - slow EMA
        # Need to align arrays since slow EMA starts later
        offset = self.slow_period - self.fast_period
        macd_line = [fast_ema[i + offset] - slow_ema[i] for i in range(len(slow_ema))]
        
        # Signal line = EMA of MACD line
        signal_line = self.calculate_ema(macd_line, self.signal_period)
        
        # Histogram = MACD line - signal line
        # Need to align arrays
        offset = len(macd_line) - len(signal_line)
        histogram = [macd_line[i + offset] - signal_line[i] for i in range(len(signal_line))]
        
        return macd_line, signal_line, histogram
    
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
    
    def buy_signal(self, candles: List[Tuple]) -> bool:
        """
        Generate buy signal from either normal MACD or greedy logic.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should buy, False otherwise
        """
        if len(candles) < self.min_candles:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Check greedy buy first (takes priority when patient)
        if self.greedy_buy_signal(current_price):
            if self.would_be_profitable_buy(current_price):
                # Reset counters on successful signal
                self.candles_since_last_trade = 0
                self.impatient_candles = 0
                self.last_buy_price = current_price
                return True
        
        # Normal MACD buy signal
        macd_line, signal_line, histogram = self.calculate_macd(candles)
        
        if len(histogram) < 2:
            self.candles_since_last_trade += 1
            if not self.is_price_profitable(current_price):
                self.impatient_candles += 1
            else:
                self.impatient_candles = 0
            return False
        
        # Buy when histogram crosses from negative to positive (bullish crossover)
        macd_buy = histogram[-2] <= 0 and histogram[-1] > 0
        
        if macd_buy:
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
    
    def sell_signal(self, candles: List[Tuple]) -> bool:
        """
        Generate sell signal from either normal MACD or greedy logic.
        
        Args:
            candles: Historical candle data
            
        Returns:
            True if should sell, False otherwise
        """
        if len(candles) < self.min_candles:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Check greedy sell first (takes priority when patient)
        if self.greedy_sell_signal(current_price):
            if self.would_be_profitable_sell(current_price):
                # Reset counters on successful signal
                self.candles_since_last_trade = 0
                self.impatient_candles = 0
                self.last_sell_price = current_price
                return True
        
        # Normal MACD sell signal
        macd_line, signal_line, histogram = self.calculate_macd(candles)
        
        if len(histogram) < 2:
            self.candles_since_last_trade += 1
            if not self.is_price_profitable(current_price):
                self.impatient_candles += 1
            else:
                self.impatient_candles = 0
            return False
        
        # Sell when histogram crosses from positive to negative (bearish crossover)
        macd_sell = histogram[-2] >= 0 and histogram[-1] < 0
        
        if macd_sell:
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
        return f"Greedy MACD ({self.fast_period}/{self.slow_period}/{self.signal_period})"
    
    def explain(self) -> List[str]:
        """Provide explanation of the strategy."""
        greedy_status = "🟢 GREEDY MODE" if self.is_greedy_mode() else "⏳ Normal Mode"
        candles_left = max(0, self.patience_candles - self.impatient_candles)
        
        lines = [
            f"📊💰 Greedy MACD Strategy ({self.fast_period}/{self.slow_period}/{self.signal_period})",
            f"   • Normal: Buy on bullish crossover, Sell on bearish crossover",
            f"   • Greedy: After {self.patience_candles} unprofitable candles ({self.patience_candles * 5 // 60}h @ 5min), take {self.profit_margin}% profit",
            f"   • Fee Rate: {self.fee_rate*100:.4f}%",
            f"   • Loss Tolerance: {self.loss_tolerance*100:.2f}%",
            f"   • Status: {greedy_status} ({candles_left} unprofitable candles until greedy)",
            f"   • Candles since last trade: {self.candles_since_last_trade}",
            f"   • Impatient candles (unprofitable): {self.impatient_candles}",
            f"   • Economics-aware: only signals profitable trades"
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
