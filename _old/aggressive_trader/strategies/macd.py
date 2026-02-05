"""
MACD (Moving Average Convergence Divergence) Strategy

Buy Signal: MACD line crosses above Signal line (bullish crossover)
Sell Signal: MACD line crosses below Signal line (bearish crossover)

Parameters:
- fast_period: Fast EMA period (default: 12)
- slow_period: Slow EMA period (default: 26)
- signal_period: Signal line EMA period (default: 9)
"""

from typing import List, Dict, Optional
import sys
import os

# Handle imports for both package and direct execution
try:
    from .base import AggressiveStrategy, EntrySignal, Candle, SignalStrength
    from ..position import PositionSide
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from strategies.base import AggressiveStrategy, EntrySignal, Candle, SignalStrength
    from position import PositionSide


class MACDStrategy(AggressiveStrategy):
    """
    MACD Crossover Strategy
    
    Goes LONG when MACD crosses above Signal line
    Goes SHORT (or exits) when MACD crosses below Signal line
    """
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
                 bot=None, fee_rate: float = 0.0025):
        super().__init__(bot=bot, fee_rate=fee_rate)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.name = f"MACD({fast_period},{slow_period},{signal_period})"
        
        # Store previous values for crossover detection
        self.prev_macd = None
        self.prev_signal = None
        
    def _calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return []
        
        ema = []
        multiplier = 2 / (period + 1)
        
        # Start with SMA for first value
        sma = sum(prices[:period]) / period
        ema.append(sma)
        
        # Calculate EMA for remaining values
        for i in range(period, len(prices)):
            ema_val = (prices[i] * multiplier) + (ema[-1] * (1 - multiplier))
            ema.append(ema_val)
            
        return ema
    
    def _calculate_macd(self, prices: List[float]) -> Dict[str, Optional[float]]:
        """
        Calculate MACD components
        
        Returns:
            dict with 'macd', 'signal', 'histogram' values (or None if not enough data)
        """
        if len(prices) < self.slow_period + self.signal_period:
            return {'macd': None, 'signal': None, 'histogram': None}
        
        # Calculate fast and slow EMAs
        fast_ema = self._calculate_ema(prices, self.fast_period)
        slow_ema = self._calculate_ema(prices, self.slow_period)
        
        if not fast_ema or not slow_ema:
            return {'macd': None, 'signal': None, 'histogram': None}
        
        # MACD line = Fast EMA - Slow EMA
        # Align the EMAs (slow EMA starts later)
        offset = self.slow_period - self.fast_period
        macd_line = []
        for i in range(len(slow_ema)):
            macd_val = fast_ema[i + offset] - slow_ema[i]
            macd_line.append(macd_val)
        
        if len(macd_line) < self.signal_period:
            return {'macd': None, 'signal': None, 'histogram': None}
        
        # Signal line = EMA of MACD line
        signal_line = self._calculate_ema(macd_line, self.signal_period)
        
        if not signal_line:
            return {'macd': None, 'signal': None, 'histogram': None}
        
        # Get current values
        current_macd = macd_line[-1]
        current_signal = signal_line[-1]
        histogram = current_macd - current_signal
        
        return {
            'macd': current_macd,
            'signal': current_signal,
            'histogram': histogram
        }
    
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        """
        Generate entry signal based on MACD crossover
        
        Returns:
            EntrySignal for LONG on bullish crossover
            None otherwise (we don't short in this version)
        """
        min_candles = self.slow_period + self.signal_period + 1
        if len(candles) < min_candles:
            return None
        
        # Get closing prices
        closes = [c.close for c in candles]
        
        # Calculate current MACD
        macd_data = self._calculate_macd(closes)
        
        if macd_data['macd'] is None:
            return None
        
        current_macd = macd_data['macd']
        current_signal = macd_data['signal']
        histogram = macd_data['histogram']
        
        signal = None
        
        # Check for crossover if we have previous values
        if self.prev_macd is not None and self.prev_signal is not None:
            # Bullish crossover: MACD crosses above Signal
            if self.prev_macd <= self.prev_signal and current_macd > current_signal:
                # Determine signal strength based on histogram
                if abs(histogram) > 50:  # Strong momentum
                    strength = SignalStrength.STRONG
                elif abs(histogram) > 20:
                    strength = SignalStrength.MODERATE
                else:
                    strength = SignalStrength.WEAK
                
                signal = EntrySignal(
                    side=PositionSide.LONG,
                    strength=strength,
                    stop_loss_pct=self.default_stop_loss_pct,
                    take_profit_pct=self.default_take_profit_pct,
                    use_trailing_stop=self.use_trailing_stop,
                    reason=f"MACD bullish crossover (histogram: {histogram:.2f})"
                )
        
        # Store for next iteration
        self.prev_macd = current_macd
        self.prev_signal = current_signal
        
        return signal
    
    def should_exit_early(self, candles: List[Candle], current_price: float,
                          entry_price: float, side: PositionSide) -> bool:
        """
        Exit on bearish crossover (MACD crosses below signal)
        """
        if len(candles) < self.slow_period + self.signal_period + 1:
            return False
        
        closes = [c.close for c in candles]
        macd_data = self._calculate_macd(closes)
        
        if macd_data['macd'] is None or self.prev_macd is None:
            return False
        
        # Exit LONG on bearish crossover
        if side == PositionSide.LONG:
            if self.prev_macd >= self.prev_signal and macd_data['macd'] < macd_data['signal']:
                return True
        
        return False
    
    def get_indicators(self, candles: List[Candle]) -> Dict:
        """Get current indicator values for display"""
        closes = [c.close for c in candles]
        macd_data = self._calculate_macd(closes)
        
        return {
            'macd': macd_data['macd'],
            'signal': macd_data['signal'],
            'histogram': macd_data['histogram'],
            'trend': 'bullish' if macd_data['histogram'] and macd_data['histogram'] > 0 else 'bearish'
        }
    
    def get_name(self) -> str:
        return self.name


class MACDHistogramStrategy(AggressiveStrategy):
    """
    MACD Histogram Strategy
    
    More aggressive than crossover - trades based on histogram turning positive
    Goes LONG when histogram becomes positive after being negative
    """
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
                 histogram_threshold: float = 0.0, bot=None, fee_rate: float = 0.0025):
        super().__init__(bot=bot, fee_rate=fee_rate)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.histogram_threshold = histogram_threshold
        self.name = f"MACD-Histogram({fast_period},{slow_period},{signal_period})"
        
        self.prev_histogram = None
        self.macd_calc = MACDStrategy(fast_period, slow_period, signal_period)
        
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        """Generate signal based on histogram direction change"""
        min_candles = self.slow_period + self.signal_period + 2
        if len(candles) < min_candles:
            return None
        
        closes = [c.close for c in candles]
        macd_data = self.macd_calc._calculate_macd(closes)
        
        if macd_data['histogram'] is None:
            return None
        
        histogram = macd_data['histogram']
        signal = None
        
        if self.prev_histogram is not None:
            # Histogram crosses above threshold (turning bullish)
            if self.prev_histogram <= self.histogram_threshold and histogram > self.histogram_threshold:
                signal = EntrySignal(
                    side=PositionSide.LONG,
                    strength=SignalStrength.MODERATE,
                    stop_loss_pct=self.default_stop_loss_pct,
                    take_profit_pct=self.default_take_profit_pct,
                    use_trailing_stop=self.use_trailing_stop,
                    reason=f"MACD histogram turned positive ({histogram:.2f})"
                )
        
        self.prev_histogram = histogram
        return signal
    
    def should_exit_early(self, candles: List[Candle], current_price: float,
                          entry_price: float, side: PositionSide) -> bool:
        """Exit when histogram turns negative"""
        if len(candles) < self.slow_period + self.signal_period + 2:
            return False
        
        closes = [c.close for c in candles]
        macd_data = self.macd_calc._calculate_macd(closes)
        
        if macd_data['histogram'] is None:
            return False
        
        # Exit LONG when histogram turns negative
        if side == PositionSide.LONG and macd_data['histogram'] < -self.histogram_threshold:
            return True
        
        return False
    
    def get_name(self) -> str:
        return self.name


# Test the strategy
if __name__ == "__main__":
    import random
    
    candles = []
    price = 100000
    for i in range(100):
        change = random.uniform(-500, 500)
        price += change
        candles.append(Candle(
            timestamp=i,
            open=price - change/2,
            high=price + abs(change),
            low=price - abs(change),
            close=price,
            volume=random.uniform(100, 1000)
        ))
    
    strategy = MACDStrategy()
    
    for i in range(50, len(candles)):
        signal = strategy.should_enter(candles[:i+1], candles[i].close)
        if signal:
            print(f"Candle {i}: {signal.side.value} signal - {signal.reason}")
