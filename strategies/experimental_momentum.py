"""
Greedy Trend Mom Trading Strategy

Combines Grumpy Mom's greedy mechanism with a trend filter:
- Uses SMA to determine trend direction
- Greedy BUY only allowed when price is ABOVE SMA (uptrend)
- Greedy SELL only allowed when price is BELOW SMA (downtrend)
- Normal momentum signals work regardless of trend

The idea: Don't catch falling knives (greedy buy in downtrend)
         Don't sell rallies early (greedy sell in uptrend)

ECONOMICS-AWARE:
- Strategy now has direct access to fee_rate and loss_tolerance
- Uses would_be_profitable_buy/sell() to check profitability BEFORE signaling
"""

from typing import List
from .base import Strategy


class ExperimentalMomentumStrategy(Strategy):
    """
    Greedy Trend Mom - Grumpy Mom with trend-filtered greedy trades.
    
    Now economics-aware: checks profitability including fees before signaling.
    """
    
    def __init__(self, bot, period: int = 14, buy_threshold: float = 1.0, 
                 sell_threshold: float = -1.0, profit_margin: float = 1.0,
                 patience_candles: int = 1440, trend_period: int = 200,
                 require_trend_alignment: bool = True,
                 fee_rate: float = 0.0, loss_tolerance: float = 0.0):
        """
        Initialize Greedy Trend Mom strategy.
        
        Args:
            bot: Bot instance
            period: ROC lookback period (default 14)
            buy_threshold: ROC % for momentum buy (default 1.0%)
            sell_threshold: ROC % for momentum sell (default -1.0%)
            profit_margin: % profit for greedy trades (default 1.0%)
            patience_candles: Candles before greedy mode (default 1440)
            trend_period: SMA period for trend (default 200)
            require_trend_alignment: Filter greedy by trend (default True)
            fee_rate: Trading fee rate as decimal (e.g., 0.0025 for 0.25%)
            loss_tolerance: Max acceptable loss as decimal (e.g., 0.0 for no losses)
        """
        super().__init__(bot, fee_rate=fee_rate, loss_tolerance=loss_tolerance)
        self.period = period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.profit_margin = profit_margin
        self.patience_candles = patience_candles
        self.trend_period = trend_period
        self.require_trend_alignment = require_trend_alignment
        
        self.min_candles = max(period + 1, trend_period + 1)
        
        # Greedy tracking (same as Grumpy Mom)
        self.candles_since_last_trade = 0
        self.impatient_candles = 0
        self.last_buy_price = None
        self.last_sell_price = None
        
        # Trend tracking
        self.is_uptrend = None
        self.current_sma = 0.0
        
        self._closes_cache = []
        
    def __str__(self):
        return (f"GreedyTrendMom(margin={self.profit_margin}%, "
                f"sma={self.trend_period}, patience={self.patience_candles}, fee={self.fee_rate*100:.3f}%)")
    
    @property
    def name(self):
        return str(self)
    
    def calculate_sma(self, prices: List[float], period: int) -> float:
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        return sum(prices[-period:]) / period
    
    def update_trend(self, prices: List[float], current_price: float):
        if len(prices) >= self.trend_period:
            self.current_sma = self.calculate_sma(prices, self.trend_period)
            self.is_uptrend = current_price > self.current_sma
        else:
            self.is_uptrend = None
    
    def calculate_roc(self, prices: List[float]) -> float:
        if len(prices) < self.period + 1:
            return 0.0
        old_price = prices[-(self.period + 1)]
        current_price = prices[-1]
        if old_price == 0:
            return 0.0
        return ((current_price - old_price) / old_price) * 100
    
    def is_greedy_mode(self) -> bool:
        return self.impatient_candles >= self.patience_candles
    
    def greedy_buy_allowed(self) -> bool:
        if not self.require_trend_alignment:
            return True
        return self.is_uptrend is None or self.is_uptrend
    
    def greedy_sell_allowed(self) -> bool:
        if not self.require_trend_alignment:
            return True
        return self.is_uptrend is None or not self.is_uptrend
    
    def greedy_buy_signal(self, current_price: float) -> bool:
        if not self.is_greedy_mode():
            return False
        if self.last_sell_price is None:
            return False
        if not self.greedy_buy_allowed():
            return False
        target = self.last_sell_price * (1 - self.profit_margin / 100)
        return current_price <= target
    
    def greedy_sell_signal(self, current_price: float) -> bool:
        if not self.is_greedy_mode():
            return False
        if self.last_buy_price is None:
            return False
        if not self.greedy_sell_allowed():
            return False
        target = self.last_buy_price * (1 + self.profit_margin / 100)
        return current_price >= target
    
    def is_price_profitable(self, current_price: float) -> bool:
        position = self.bot.position
        if position == "short" and self.last_sell_price:
            target = self.last_sell_price * (1 - self.profit_margin / 100)
            return current_price <= target
        elif position == "long" and self.last_buy_price:
            target = self.last_buy_price * (1 + self.profit_margin / 100)
            return current_price >= target
        return False
    
    def buy_signal(self, candles: List) -> bool:
        if len(candles) < self.min_candles + 1:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Update cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        self.update_trend(self._closes_cache, current_price)
        
        # Greedy buy (trend-filtered)
        if self.greedy_buy_signal(current_price):
            # CRITICAL: Check if trade would be profitable after fees
            if not self.would_be_profitable_buy(current_price):
                self.candles_since_last_trade += 1
                self.impatient_candles += 1
                return False
            self.candles_since_last_trade = 0
            self.impatient_candles = 0
            self.last_buy_price = current_price
            return True
        
        # Normal momentum buy
        current_roc = self.calculate_roc(self._closes_cache)
        previous_roc = self.calculate_roc(self._closes_cache[:-1])
        
        if previous_roc <= self.buy_threshold and current_roc > self.buy_threshold:
            # CRITICAL: Check if trade would be profitable after fees
            if not self.would_be_profitable_buy(current_price):
                self.candles_since_last_trade += 1
                self.impatient_candles += 1
                return False
            self.candles_since_last_trade = 0
            self.impatient_candles = 0
            self.last_buy_price = current_price
            return True
        
        self.candles_since_last_trade += 1
        if not self.is_price_profitable(current_price):
            self.impatient_candles += 1
        else:
            self.impatient_candles = 0
        
        return False
    
    def sell_signal(self, candles: List) -> bool:
        if len(candles) < self.min_candles + 1:
            self.candles_since_last_trade += 1
            return False
        
        current_price = candles[-1][4]
        
        # Update cache
        if len(self._closes_cache) < len(candles):
            if not self._closes_cache:
                self._closes_cache = [c[4] for c in candles]
            else:
                self._closes_cache.extend([c[4] for c in candles[len(self._closes_cache):]])
        
        self.update_trend(self._closes_cache, current_price)
        
        # Greedy sell (trend-filtered)
        if self.greedy_sell_signal(current_price):
            # CRITICAL: Check if trade would be profitable after fees
            if not self.would_be_profitable_sell(current_price):
                self.candles_since_last_trade += 1
                self.impatient_candles += 1
                return False
            self.candles_since_last_trade = 0
            self.impatient_candles = 0
            self.last_sell_price = current_price
            return True
        
        # Normal momentum sell
        current_roc = self.calculate_roc(self._closes_cache)
        previous_roc = self.calculate_roc(self._closes_cache[:-1])
        
        if previous_roc >= self.sell_threshold and current_roc < self.sell_threshold:
            # CRITICAL: Check if trade would be profitable after fees
            if not self.would_be_profitable_sell(current_price):
                self.candles_since_last_trade += 1
                self.impatient_candles += 1
                return False
            self.candles_since_last_trade = 0
            self.impatient_candles = 0
            self.last_sell_price = current_price
            return True
        
        self.candles_since_last_trade += 1
        if not self.is_price_profitable(current_price):
            self.impatient_candles += 1
        else:
            self.impatient_candles = 0
        
        return False
    
    def explain(self) -> List[str]:
        greedy = "🟢 GREEDY" if self.is_greedy_mode() else "⏳ Normal"
        trend = "📈 UP" if self.is_uptrend else ("📉 DOWN" if self.is_uptrend is False else "❓")
        return [
            f"⚡🎯 Greedy Trend Mom",
            f"   • Margin: {self.profit_margin}%, SMA: {self.trend_period}",
            f"   • Fee Rate: {self.fee_rate*100:.4f}%",
            f"   • Loss Tolerance: {self.loss_tolerance*100:.2f}%",
            f"   • {greedy} | {trend} (SMA: ${self.current_sma:,.0f})",
            f"   • Greedy buy: {'✅' if self.greedy_buy_allowed() else '❌'} | sell: {'✅' if self.greedy_sell_allowed() else '❌'}",
            f"   • Economics-aware: only signals profitable trades"
        ]
