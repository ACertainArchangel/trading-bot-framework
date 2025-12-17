from typing import List, Tuple
from .base import Strategy

class MACDStrategy(Strategy):
    """
    MACD (Moving Average Convergence Divergence) crossover strategy.
    
    Signals:
    - BUY when MACD line crosses above signal line (bullish crossover)
    - SELL when MACD line crosses below signal line (bearish crossover)
    
    Also checks baseline to avoid trades that would result in a loss.
    """
    
    def __init__(self, bot, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
                 min_slope_periods: int = 3, min_momentum_strength: float = 2.0,
                 trajectory_threshold: float = 0.7, sharp_reversal_multiplier: float = 3.0):
        """
        Initialize MACD strategy with trajectory-based prediction.
        
        Args:
            bot: The Bot instance
            fast_period: Period for fast EMA (default 12)
            slow_period: Period for slow EMA (default 26)
            signal_period: Period for signal line EMA (default 9)
            min_slope_periods: Periods to check for consistent slope (default 3)
            min_momentum_strength: Minimum histogram acceleration required (default 2.0)
            trajectory_threshold: How close to zero to predict crossover (default 0.7 = 70% of way to zero)
            sharp_reversal_multiplier: Multiplier for detecting sharp reversals (default 3.0)
        """
        super().__init__(bot)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.min_slope_periods = min_slope_periods
        self.min_momentum_strength = min_momentum_strength
        self.trajectory_threshold = trajectory_threshold
        self.sharp_reversal_multiplier = sharp_reversal_multiplier
        
        # Need at least slow_period + signal_period candles for accurate MACD
        self.min_candles = slow_period + signal_period + min_slope_periods
        
        # Cache for performance
        self._closes_cache = []
    
    def __str__(self):
        return (f"MACDStrategy(fast={self.fast_period}, slow={self.slow_period}, signal={self.signal_period}, "
                f"trajectory={self.trajectory_threshold}, sharp_reversal={self.sharp_reversal_multiplier}x, "
                f"momentum={self.min_momentum_strength}x)")
    
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
    
    def predict_crossover(self, histogram: List[float], direction: str) -> dict:
        """
        Predict if histogram is on trajectory to cross zero based on momentum and slope.
        This allows jumping in BEFORE the actual crossover when trajectory is clear.
        
        Args:
            histogram: MACD histogram values
            direction: 'bullish' (heading toward positive) or 'bearish' (heading toward negative)
            
        Returns:
            dict with 'will_cross' (bool), 'confidence' (float), 'is_sharp_reversal' (bool)
        """
        if len(histogram) < self.min_slope_periods + 1:
            return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
        
        # Get recent histogram values for trajectory analysis
        recent = histogram[-(self.min_slope_periods + 1):]
        
        if direction == 'bullish':
            # For bullish trajectory (heading toward zero from below):
            
            # 1. Must currently be negative and moving upward
            if recent[-1] >= 0:
                return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
            
            # 2. Check for consistent upward slope
            slope_consistent = all(recent[i] > recent[i-1] for i in range(1, len(recent)))
            if not slope_consistent:
                return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
            
            # 3. Calculate slope acceleration
            early_slope = recent[1] - recent[0]
            late_slope = recent[-1] - recent[-2]
            
            if early_slope <= 0:
                return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
            
            acceleration = late_slope / early_slope if early_slope != 0 else 0
            
            # 4. Check if we're on trajectory to cross zero
            # Calculate how many periods until zero based on current slope
            if late_slope > 0:
                periods_to_zero = abs(recent[-1]) / late_slope
                
                # If we'll reach zero in next 1-3 candles, we're on trajectory
                on_trajectory = periods_to_zero <= 3
                
                # Confidence based on how close we are and how strong the momentum
                distance_from_zero = abs(recent[-1])
                max_distance = max(abs(min(recent)), distance_from_zero * 2)
                proximity = 1.0 - (distance_from_zero / max_distance) if max_distance > 0 else 0
                
                # High confidence if: close to zero + strong acceleration
                confidence = proximity * min(acceleration / self.min_momentum_strength, 1.5)
                
                # Detect sharp reversal: very strong acceleration from deep negative
                is_sharp_reversal = (acceleration >= self.sharp_reversal_multiplier and 
                                    distance_from_zero > abs(recent[0]) * 0.3)
                
                # Accept if confidence exceeds threshold OR if sharp reversal
                will_cross = (confidence >= self.trajectory_threshold or 
                             (is_sharp_reversal and acceleration >= self.min_momentum_strength))
                
                return {
                    'will_cross': will_cross and on_trajectory,
                    'confidence': confidence,
                    'is_sharp_reversal': is_sharp_reversal,
                    'periods_to_zero': periods_to_zero,
                    'acceleration': acceleration
                }
        
        elif direction == 'bearish':
            # For bearish trajectory (heading toward zero from above):
            
            # 1. Must currently be positive and moving downward
            if recent[-1] <= 0:
                return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
            
            # 2. Check for consistent downward slope
            slope_consistent = all(recent[i] < recent[i-1] for i in range(1, len(recent)))
            if not slope_consistent:
                return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
            
            # 3. Calculate slope acceleration (downward)
            early_slope = recent[0] - recent[1]  # Positive value for downward movement
            late_slope = recent[-2] - recent[-1]
            
            if early_slope <= 0:
                return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
            
            acceleration = late_slope / early_slope if early_slope != 0 else 0
            
            # 4. Check if we're on trajectory to cross zero
            if late_slope > 0:
                periods_to_zero = recent[-1] / late_slope
                
                on_trajectory = periods_to_zero <= 3
                
                # Confidence calculation
                distance_from_zero = recent[-1]
                max_distance = max(max(recent), distance_from_zero * 2)
                proximity = 1.0 - (distance_from_zero / max_distance) if max_distance > 0 else 0
                
                confidence = proximity * min(acceleration / self.min_momentum_strength, 1.5)
                
                # Detect sharp reversal from high positive
                is_sharp_reversal = (acceleration >= self.sharp_reversal_multiplier and 
                                    distance_from_zero > recent[0] * 0.3)
                
                will_cross = (confidence >= self.trajectory_threshold or 
                             (is_sharp_reversal and acceleration >= self.min_momentum_strength))
                
                return {
                    'will_cross': will_cross and on_trajectory,
                    'confidence': confidence,
                    'is_sharp_reversal': is_sharp_reversal,
                    'periods_to_zero': periods_to_zero,
                    'acceleration': acceleration
                }
        
        return {'will_cross': False, 'confidence': 0.0, 'is_sharp_reversal': False}
    
    def buy_signal(self, candles: List[Tuple]) -> bool:
        """
        Simple MACD crossover buy signal.
        
        BUY when histogram crosses from negative to positive (bullish crossover).
        """
        if len(candles) < self.min_candles:
            return False
        
        # Calculate MACD first to always show histogram state
        macd_line, signal_line, histogram = self.calculate_macd(candles)
        
        if len(histogram) < 2:
            return False
        
        # Get timestamp for debugging
        candle_time = candles[-1][0]  # timestamp
        
        # Check position - log if we're not in short
        if self.bot.position != "short":
            # Only log crossovers we missed because we weren't in position
            if histogram[-2] <= 0 and histogram[-1] > 0:
                print(f"❌ [{candle_time}] BUY CROSSOVER MISSED: Position={self.bot.position}, Hist: {histogram[-2]:.6f} → {histogram[-1]:.6f}")
            return False
        
        # We're in short position - check for crossover
        crossover = histogram[-2] <= 0 and histogram[-1] > 0
        
        # Log histogram state when in short position (only occasionally to avoid spam)
        if len(histogram) >= 3 and histogram[-1] > histogram[-2]:
            print(f"🔍 [{candle_time}] BUY CHECK: Pos=SHORT, Hist: [{histogram[-3]:.6f}, {histogram[-2]:.6f}, {histogram[-1]:.6f}], Crossover={crossover}")
        
        if not crossover:
            return False
        
        # Check if trade would be profitable (exceed baseline)
        current_price = candles[-1][4]  # Latest close price
        baseline_check = self.check_baseline_for_buy(current_price)
        
        if baseline_check:
            print(f"✅ [{candle_time}] 📈 MACD BUY SIGNAL: Crossover! Hist: {histogram[-2]:.6f} → {histogram[-1]:.6f}, Price: ${current_price:.2f}")
        else:
            print(f"⚠️ [{candle_time}] MACD BUY crossover but baseline blocks: Would get {(self.bot.currency * (1 - self.bot.fee_rate)) / current_price:.8f}, need > {self.bot.asset_baseline:.8f}")
        
        return baseline_check
    
    def sell_signal(self, candles: List[Tuple]) -> bool:
        """
        Simple MACD crossover sell signal.
        
        SELL when histogram crosses from positive to negative (bearish crossover).
        """
        if len(candles) < self.min_candles:
            return False
        
        # Calculate MACD first to always show histogram state
        macd_line, signal_line, histogram = self.calculate_macd(candles)
        
        if len(histogram) < 2:
            return False
        
        # Get timestamp for debugging
        candle_time = candles[-1][0]  # timestamp
        
        # Check position - log if we're not in long
        if self.bot.position != "long":
            # Only log crossovers we missed because we weren't in position
            if histogram[-2] >= 0 and histogram[-1] < 0:
                print(f"❌ [{candle_time}] SELL CROSSOVER MISSED: Position={self.bot.position}, Hist: {histogram[-2]:.6f} → {histogram[-1]:.6f}")
            return False
        
        # We're in long position - check for crossover
        crossover = histogram[-2] >= 0 and histogram[-1] < 0
        
        # Log histogram state when in long position
        if len(histogram) >= 3:
            print(f"🔍 [{candle_time}] SELL CHECK: Pos=LONG, Hist: [{histogram[-3]:.6f}, {histogram[-2]:.6f}, {histogram[-1]:.6f}], Crossover={crossover}")
        
        if not crossover:
            return False
        
        # Check if trade would be profitable (exceed baseline)
        current_price = candles[-1][4]  # Latest close price
        baseline_check = self.check_baseline_for_sell(current_price)
        
        if baseline_check:
            print(f"✅ [{candle_time}] 📉 MACD SELL SIGNAL: Crossover! Hist: {histogram[-2]:.6f} → {histogram[-1]:.6f}, Price: ${current_price:.2f}")
        else:
            print(f"⚠️ [{candle_time}] MACD SELL crossover but baseline blocks: Would get {(self.bot.asset * current_price) * (1 - self.bot.fee_rate):.2f}, need > {self.bot.currency_baseline:.2f}")
        
        return baseline_check
