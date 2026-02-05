"""
Mean Reversion Strategy with Dynamic SL/TP

Concept: Prices tend to revert to their mean. Buy when oversold, sell at the mean.

Entry Signal: Price falls below lower Bollinger Band (oversold)
Take Profit: Set at the moving average (the mean we expect to revert to)
Stop Loss: Set based on ATR (Average True Range) - adapts to volatility

This is smarter than fixed SL/TP because:
1. TP is at a logical price level (the mean)
2. SL adapts to current market volatility
3. Only enters when truly oversold, not on every dip
"""

from typing import List, Dict, Optional
import sys
import os

# Handle imports for both package and direct execution
try:
    from .base import AggressiveStrategy, EntrySignal, Candle, SignalStrength
    from ..position import PositionSide
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from strategies.base import AggressiveStrategy, EntrySignal, Candle, SignalStrength
    from position import PositionSide


class MeanReversionStrategy(AggressiveStrategy):
    """
    Mean Reversion Strategy with Bollinger Bands and ATR-based stops.
    
    Entry: Price closes below lower Bollinger Band (oversold)
    TP: Dynamically set at the moving average (middle band)
    SL: Dynamically set using ATR multiplier below entry
    
    Parameters:
    - bb_period: Bollinger Band period (default: 20)
    - bb_std: Number of standard deviations for bands (default: 2.0)
    - atr_period: ATR period for volatility (default: 14)
    - atr_sl_multiplier: ATR multiplier for stop loss (default: 1.5)
    - min_distance_pct: Minimum distance from mean to enter (default: 0.5%)
    """
    
    def __init__(self, bb_period: int = 20, bb_std: float = 2.0,
                 atr_period: int = 14, atr_sl_multiplier: float = 1.5,
                 min_distance_pct: float = 0.5,
                 bot=None, fee_rate: float = 0.0025):
        super().__init__(bot=bot, fee_rate=fee_rate)
        
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.min_distance_pct = min_distance_pct / 100  # Convert to decimal
        
        self.name = f"MeanReversion(BB{bb_period}, ATR{atr_period})"
        
        # Track if we're in a position to avoid re-entry
        self.in_position = False
        self.last_entry_price = None
        
    def _calculate_sma(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period
    
    def _calculate_std(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Standard Deviation"""
        if len(prices) < period:
            return None
        mean = self._calculate_sma(prices, period)
        variance = sum((p - mean) ** 2 for p in prices[-period:]) / period
        return variance ** 0.5
    
    def _calculate_bollinger_bands(self, prices: List[float]) -> Dict[str, Optional[float]]:
        """
        Calculate Bollinger Bands
        
        Returns: dict with 'upper', 'middle', 'lower', 'width'
        """
        if len(prices) < self.bb_period:
            return {'upper': None, 'middle': None, 'lower': None, 'width': None}
        
        middle = self._calculate_sma(prices, self.bb_period)
        std = self._calculate_std(prices, self.bb_period)
        
        upper = middle + (std * self.bb_std)
        lower = middle - (std * self.bb_std)
        width = (upper - lower) / middle  # Band width as percentage
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'width': width
        }
    
    def _calculate_atr(self, candles: List[Candle]) -> Optional[float]:
        """
        Calculate Average True Range (ATR)
        
        True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
        """
        if len(candles) < self.atr_period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i-1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Use last atr_period values
        recent_tr = true_ranges[-self.atr_period:]
        return sum(recent_tr) / len(recent_tr)
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate RSI for additional confirmation"""
        if len(prices) < period + 1:
            return None
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        recent_changes = changes[-period:]
        
        gains = [c for c in recent_changes if c > 0]
        losses = [-c for c in recent_changes if c < 0]
        
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0.0001  # Avoid division by zero
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        """
        Generate entry signal when price is oversold (below lower BB)
        
        Dynamic SL/TP:
        - TP: Set at the middle band (the mean)
        - SL: Set at entry - (ATR * multiplier)
        """
        min_candles = max(self.bb_period, self.atr_period) + 1
        if len(candles) < min_candles:
            return None
        
        # Get closing prices
        closes = [c.close for c in candles]
        
        # Calculate indicators
        bb = self._calculate_bollinger_bands(closes)
        atr = self._calculate_atr(candles)
        rsi = self._calculate_rsi(closes)
        
        if bb['lower'] is None or atr is None:
            return None
        
        # Current price and band values
        lower_band = bb['lower']
        middle_band = bb['middle']
        upper_band = bb['upper']
        
        # Calculate distances
        distance_from_mean = (middle_band - current_price) / middle_band
        distance_from_lower = (current_price - lower_band) / lower_band
        
        signal = None
        
        # ENTRY CONDITIONS:
        # 1. Price is below lower Bollinger Band (oversold)
        # 2. Distance from mean is significant (worth the trade)
        # 3. RSI confirms oversold (< 35) - optional but helps
        
        is_below_lower_band = current_price < lower_band
        has_sufficient_distance = distance_from_mean >= self.min_distance_pct
        rsi_oversold = rsi is not None and rsi < 35
        
        if is_below_lower_band and has_sufficient_distance:
            # Calculate dynamic SL/TP as percentages
            # TP: Distance to mean band
            tp_distance = middle_band - current_price
            tp_pct = tp_distance / current_price
            
            # SL: Based on ATR (volatility-adjusted)
            sl_distance = atr * self.atr_sl_multiplier
            sl_pct = sl_distance / current_price
            
            # Ensure reasonable bounds
            tp_pct = max(0.003, min(tp_pct, 0.05))  # 0.3% to 5%
            sl_pct = max(0.002, min(sl_pct, 0.03))  # 0.2% to 3%
            
            # Determine signal strength
            if rsi_oversold and distance_from_mean > 0.01:  # RSI < 35 and > 1% from mean
                strength = SignalStrength.STRONG
            elif rsi_oversold or distance_from_mean > 0.008:
                strength = SignalStrength.MODERATE
            else:
                strength = SignalStrength.WEAK
            
            rsi_str = f"{rsi:.1f}" if rsi else "N/A"
            signal = EntrySignal(
                side=PositionSide.LONG,
                strength=strength,
                stop_loss_pct=sl_pct,
                take_profit_pct=tp_pct,
                use_trailing_stop=False,
                reason=f"Mean reversion: Price {distance_from_mean*100:.2f}% below mean, RSI={rsi_str}, TP={tp_pct*100:.2f}%, SL={sl_pct*100:.2f}%"
            )
            
            self.in_position = True
            self.last_entry_price = current_price
        
        return signal
    
    def should_exit_early(self, candles: List[Candle], current_price: float,
                          entry_price: float, side: PositionSide) -> bool:
        """
        Exit early if:
        1. Price reaches the upper band (overbought, take extra profit)
        2. Price crosses back above mean and starts falling again
        """
        if len(candles) < self.bb_period:
            return False
        
        closes = [c.close for c in candles]
        bb = self._calculate_bollinger_bands(closes)
        
        if bb['middle'] is None:
            return False
        
        # Exit if price reaches upper band (bonus profit)
        if side == PositionSide.LONG and current_price > bb['upper']:
            self.in_position = False
            return True
        
        return False
    
    def get_indicators(self, candles: List[Candle]) -> Dict:
        """Get current indicator values for display"""
        closes = [c.close for c in candles]
        bb = self._calculate_bollinger_bands(closes)
        atr = self._calculate_atr(candles)
        rsi = self._calculate_rsi(closes)
        
        return {
            'bb_upper': bb['upper'],
            'bb_middle': bb['middle'],
            'bb_lower': bb['lower'],
            'bb_width': bb['width'],
            'atr': atr,
            'rsi': rsi,
        }
    
    def get_name(self) -> str:
        return self.name


class RSIMeanReversionStrategy(AggressiveStrategy):
    """
    RSI-based Mean Reversion with dynamic profit targets.
    
    Simpler than Bollinger Bands - uses RSI for oversold detection.
    
    Entry: RSI < 30 (oversold)
    TP: When RSI > 50 (returned to neutral) OR fixed percentage
    SL: Based on recent swing low or ATR
    """
    
    def __init__(self, rsi_period: int = 14, rsi_oversold: float = 30,
                 rsi_neutral: float = 50, atr_period: int = 14,
                 atr_sl_multiplier: float = 2.0,
                 bot=None, fee_rate: float = 0.0025):
        super().__init__(bot=bot, fee_rate=fee_rate)
        
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_neutral = rsi_neutral
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        
        self.name = f"RSI-MeanRev(RSI{rsi_period}<{rsi_oversold})"
        
        self.prev_rsi = None
        self.cooldown = 0  # Prevent rapid re-entry
        
    def _calculate_rsi(self, prices: List[float]) -> Optional[float]:
        """Calculate RSI"""
        if len(prices) < self.rsi_period + 1:
            return None
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        recent_changes = changes[-self.rsi_period:]
        
        gains = [c for c in recent_changes if c > 0]
        losses = [-c for c in recent_changes if c < 0]
        
        avg_gain = sum(gains) / self.rsi_period if gains else 0
        avg_loss = sum(losses) / self.rsi_period if losses else 0.0001
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, candles: List[Candle]) -> Optional[float]:
        """Calculate ATR"""
        if len(candles) < self.atr_period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            true_ranges.append(tr)
        
        recent_tr = true_ranges[-self.atr_period:]
        return sum(recent_tr) / len(recent_tr)
    
    def _find_recent_swing_low(self, candles: List[Candle], lookback: int = 10) -> float:
        """Find recent swing low for stop loss placement"""
        recent = candles[-lookback:] if len(candles) >= lookback else candles
        return min(c.low for c in recent)
    
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        """Enter when RSI is oversold"""
        min_candles = max(self.rsi_period, self.atr_period) + 1
        if len(candles) < min_candles:
            return None
        
        # Cooldown between trades
        if self.cooldown > 0:
            self.cooldown -= 1
            return None
        
        closes = [c.close for c in candles]
        rsi = self._calculate_rsi(closes)
        atr = self._calculate_atr(candles)
        
        if rsi is None or atr is None:
            self.prev_rsi = rsi
            return None
        
        signal = None
        
        # Entry: RSI crosses below oversold level
        # (was above, now below - fresh oversold signal)
        is_oversold = rsi < self.rsi_oversold
        was_not_oversold = self.prev_rsi is not None and self.prev_rsi >= self.rsi_oversold
        
        if is_oversold and was_not_oversold:
            # Dynamic SL based on ATR
            sl_distance = atr * self.atr_sl_multiplier
            sl_pct = sl_distance / current_price
            
            # Dynamic TP: expect price to rise by 1.5-2x the SL distance
            # (gives us positive expected value if win rate > 40%)
            tp_pct = sl_pct * 2.0
            
            # Bounds
            sl_pct = max(0.003, min(sl_pct, 0.025))  # 0.3% to 2.5%
            tp_pct = max(0.005, min(tp_pct, 0.04))   # 0.5% to 4%
            
            strength = SignalStrength.STRONG if rsi < 25 else SignalStrength.MODERATE
            
            signal = EntrySignal(
                side=PositionSide.LONG,
                strength=strength,
                stop_loss_pct=sl_pct,
                take_profit_pct=tp_pct,
                use_trailing_stop=False,
                reason=f"RSI oversold: {rsi:.1f}, SL={sl_pct*100:.2f}%, TP={tp_pct*100:.2f}%"
            )
            
            self.cooldown = 5  # Wait 5 candles before next entry
        
        self.prev_rsi = rsi
        return signal
    
    def should_exit_early(self, candles: List[Candle], current_price: float,
                          entry_price: float, side: PositionSide) -> bool:
        """Exit when RSI returns to neutral"""
        if len(candles) < self.rsi_period + 1:
            return False
        
        closes = [c.close for c in candles]
        rsi = self._calculate_rsi(closes)
        
        if rsi is None:
            return False
        
        # Exit LONG when RSI returns to neutral/overbought
        if side == PositionSide.LONG and rsi > self.rsi_neutral:
            self.cooldown = 3  # Brief cooldown after exit
            return True
        
        return False
    
    def get_name(self) -> str:
        return self.name


# Test
if __name__ == "__main__":
    import random
    
    # Generate test data with mean-reverting behavior
    candles = []
    price = 100000
    mean = 100000
    
    for i in range(200):
        # Mean-reverting random walk
        reversion = (mean - price) * 0.02  # Pull toward mean
        noise = random.uniform(-300, 300)
        price += reversion + noise
        
        candles.append(Candle(
            timestamp=i,
            open=price - noise/2,
            high=price + abs(noise) + random.uniform(0, 100),
            low=price - abs(noise) - random.uniform(0, 100),
            close=price,
            volume=random.uniform(100, 1000)
        ))
    
    strategy = MeanReversionStrategy()
    
    for i in range(50, len(candles)):
        signal = strategy.should_enter(candles[:i+1], candles[i].close)
        if signal:
            print(f"Candle {i}: {signal.reason}")
