"""
SuperStrat - EMA crossover + breakout strategy with confirmation indicators.

The high-level logic is implemented here, while individual indicators are in the indicators/ folder.
Currently only supports LONG positions.

Entry Logic:
    Primary triggers (ONE required):
        - Golden cross: Short EMA crosses ABOVE Long EMA (exact moment)
        - Breakout: Price breaks above recent N-period high
    
    Confirmations (strengthen signal):
        - Volume spike (especially bullish)
        - RSI not overbought (room to run)
        - Inverse Head & Shoulders pattern
        - Bullish EMA trend (for breakouts)
    
    Rejections (block entry):
        - RSI overbought (>70) - no room to run
        - At strong resistance level (for golden cross only, not breakouts)
        - Negative trendline slope (30-candle linear regression)
    
Exit Logic:
    Primary trigger:
        - Death cross: Short EMA crosses BELOW Long EMA
    
    Early exit signals:
        - Head and Shoulders top pattern
        - RSI overbought + volume spike (distribution)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import sys
import os

# Handle imports for both package and direct execution
try:
    from .indicators.head_and_shoulders import HeadAndShouldersIndicator
    from .indicators.support_resistance import SupportResistanceIndicator
    from .indicators.ema import EMAIndicator
    from .indicators.volume_spike import VolumeSpikeIndicator
    from .indicators.rsi import RSIIndicator
    from .base import AggressiveStrategy, EntrySignal, Candle, SignalStrength
    from ..position import PositionSide
except ImportError:
    # Add strategies directory to path for direct execution from test_agro.py
    strategies_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(strategies_dir)
    if strategies_dir not in sys.path:
        sys.path.insert(0, strategies_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    from indicators.head_and_shoulders import HeadAndShouldersIndicator
    from indicators.support_resistance import SupportResistanceIndicator
    from indicators.ema import EMAIndicator
    from indicators.volume_spike import VolumeSpikeIndicator
    from indicators.rsi import RSIIndicator
    from base import AggressiveStrategy, EntrySignal, Candle, SignalStrength
    from position import PositionSide


@dataclass
class IndicatorState:
    """Holds the current state of all indicators for decision making."""
    # EMA state - PRIMARY TRIGGER
    golden_cross_now: bool = False     # Short EMA just crossed above long EMA THIS candle
    death_cross_now: bool = False      # Short EMA just crossed below long EMA THIS candle
    ema_trend_bullish: bool = False    # Short EMA > Long EMA
    ema_spread_pct: float = 0.0        # How far apart the EMAs are (momentum indicator)
    
    # Breakout state - ALTERNATIVE PRIMARY TRIGGER
    breakout_detected: bool = False    # Price broke above recent high
    breakout_high: float = 0.0         # The high that was broken
    breakout_strength_pct: float = 0.0 # How far above the breakout level (% above)
    
    # Trendline state - REJECTION
    trendline_slope: float = 0.0       # Linear regression slope (positive = uptrend)
    trendline_slope_pct: float = 0.0   # Slope as % per candle
    trendline_bullish: bool = False    # Slope > 0
    
    # Pattern state - CONFIRMATION/EARLY EXIT
    inverse_hns_detected: bool = False  # Bullish reversal pattern
    hns_top_detected: bool = False      # Bearish reversal pattern
    
    # Volume state - CONFIRMATION
    volume_spike: bool = False
    volume_spike_bullish: bool = False  # Spike with price increase
    volume_spike_bearish: bool = False  # Spike with price decrease
    
    # Support/Resistance levels - REJECTION / RISK MGMT
    nearest_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    near_resistance: bool = False       # Price within 0.5% of resistance
    
    # Market regime (RSI-based) - CONFIRMATION/REJECTION
    rsi: float = 50.0
    market_regime: str = 'neutral'  # 'bearish', 'neutral', 'bullish'
    regime_strength: float = 0.0    # 0-1 how strong the regime is
    is_oversold: bool = False       # RSI < 30 - good for longs
    is_overbought: bool = False     # RSI > 70 - REJECT long entry


class SuperStrat(AggressiveStrategy):
    """
    EMA crossover strategy with confirmation indicators.
    
    Entry: Golden cross (short EMA crosses above long EMA)
    Exit: Death cross (short EMA crosses below long EMA) or early exit signals
    
    Confirmations (improve signal strength):
        - Volume spike
        - RSI not overbought
        - Inverse H&S pattern
    
    Rejections (block entry):
        - RSI overbought
        - Price at resistance
    
    Risk Management:
        - Stop-loss at support or percentage-based
        - Take-profit adapts to market regime (RSI)
    """
    
    # Minimum candles required for analysis
    MIN_CANDLES = 50
    
    # Breakout detection settings
    BREAKOUT_LOOKBACK = 20         # Candles to look back for recent high
    BREAKOUT_MIN_STRENGTH = 0.001  # Minimum % above breakout level (0.1%)
    
    # Trendline regression settings
    TRENDLINE_LOOKBACK = 30        # Candles for linear regression
    TRENDLINE_REJECT_NEGATIVE = True  # Reject entry if slope is negative
    
    # Risk/reward settings (0 = disabled, use fixed TP from defaults)
    MIN_RISK_REWARD_RATIO = 0
    # These are DECIMALS: 0.001 = 0.1%, 0.01 = 1%, 0.1 = 10%
    DEFAULT_STOP_LOSS_PCT = 0.001    # 0.1%
    DEFAULT_TAKE_PROFIT_PCT = 0.001  # 0.06%
    
    # Separate scaling factors for SL and TP
    # Use smaller values for tighter brackets (e.g., 0.5 = half the width)
    # Useful for 1m timeframe where moves are smaller
    DEFAULT_SL_SCALE = 1   # Multiplier on default SL
    DEFAULT_TP_SCALE = 1   # Multiplier on default TP
    
    # Market regime thresholds (RSI-based)
    RSI_BEARISH_THRESHOLD = 40
    RSI_BULLISH_THRESHOLD = 60
    
    # ==========================================================================
    # SIGNAL STRENGTH SCALING FACTORS
    # Stronger signals = tighter SL (more confident), wider TP (expect bigger move)
    # ==========================================================================
    SL_STRENGTH_STRONG = 1.0      # Tighter SL for strong signals
    SL_STRENGTH_MODERATE = 1.0    # Base SL
    SL_STRENGTH_WEAK = 1.0        # Wider SL for weak signals (more room)
    
    TP_STRENGTH_STRONG = 2      # Wider TP for strong signals (expect bigger move)
    TP_STRENGTH_MODERATE = 1.4    # Base TP
    TP_STRENGTH_WEAK = 1.0        # Tighter TP for weak signals (take profits early)
    
    # ==========================================================================
    # TREND SCALING FACTORS
    # Trading WITH trend = wider TP, tighter SL
    # Trading AGAINST trend = tighter TP, wider SL
    # ==========================================================================
    # For LONG positions:
    SL_TREND_BULLISH = 0.8        # Tighter SL in uptrend (trend support)
    SL_TREND_NEUTRAL = 1.0        # Base SL
    SL_TREND_BEARISH = 1.5        # Wider SL against trend (more volatility)
    
    TP_TREND_BULLISH = 1.5        # Wider TP in uptrend (let it run)
    TP_TREND_NEUTRAL = 1.0        # Base TP
    TP_TREND_BEARISH = 0.6        # Tighter TP against trend (take quick profits)
    
    def __init__(self, ema_short_period: int = 9, ema_long_period: int = 21,
                 volume_spike_threshold: float = 2.0, volume_lookback: int = 20,
                 sr_lookback: int = 50, sl_scale: float = None, tp_scale: float = None,
                 bot=None, fee_rate: float = 0.0025):
        """
        Initialize SuperStrat with configurable indicator parameters.
        
        Args:
            ema_short_period: Short EMA period for crossover detection (default 9)
            ema_long_period: Long EMA period for crossover detection (default 21)
            volume_spike_threshold: Multiplier above avg volume for spike detection (default 2.0)
            volume_lookback: Periods for average volume calculation (default 20)
            sr_lookback: Periods for support/resistance detection (default 50)
            sl_scale: Scaling factor for stop-loss (default 0.5 = 1% base SL)
            tp_scale: Scaling factor for take-profit (default 0.5 = 2% base TP)
            bot: Reference to trading bot
            fee_rate: Trading fee rate as decimal
        """
        super().__init__(bot=bot, fee_rate=fee_rate)
        
        # Store parameters - use class defaults if not provided
        self.ema_short_period = ema_short_period
        self.ema_long_period = ema_long_period
        self.volume_spike_threshold = volume_spike_threshold
        self.volume_lookback = volume_lookback
        self.sr_lookback = sr_lookback
        self.sl_scale = sl_scale if sl_scale is not None else self.DEFAULT_SL_SCALE
        self.tp_scale = tp_scale if tp_scale is not None else self.DEFAULT_TP_SCALE
        
        # Initialize indicators
        self.ema_short = EMAIndicator(ema_short_period)
        self.ema_long = EMAIndicator(ema_long_period)
        self.hns_indicator = HeadAndShouldersIndicator()
        self.volume_spike_indicator = VolumeSpikeIndicator(
            threshold=volume_spike_threshold, 
            lookback=volume_lookback
        )
        self.sr_indicator = SupportResistanceIndicator(lookback=sr_lookback)
        self.rsi_indicator = RSIIndicator(period=14)
        
        self.name = "SuperStrat"
    
    def _extract_closes(self, candles: List[Candle]) -> List[float]:
        """Extract close prices from candle list."""
        return [c.close for c in candles]
    
    def _extract_volumes(self, candles: List[Candle]) -> List[float]:
        """Extract volumes from candle list."""
        return [c.volume for c in candles]
    
    def _extract_highs(self, candles: List[Candle]) -> List[float]:
        """Extract high prices from candle list."""
        return [c.high for c in candles]
    
    def _extract_lows(self, candles: List[Candle]) -> List[float]:
        """Extract low prices from candle list."""
        return [c.low for c in candles]
    
    def _calculate_trendline_slope(self, prices: List[float]) -> Tuple[float, float]:
        """
        Calculate linear regression slope of prices.
        
        Uses simple linear regression (least squares) to fit a line
        through the price data and return the slope.
        
        Args:
            prices: List of prices (most recent last)
            
        Returns:
            Tuple of (slope, slope_pct_per_candle)
            slope: Raw slope in price units per candle
            slope_pct: Slope as percentage of mean price per candle
        """
        n = len(prices)
        if n < 2:
            return 0.0, 0.0
        
        # Simple linear regression: y = mx + b
        # Using least squares: m = (n*sum(xy) - sum(x)*sum(y)) / (n*sum(x^2) - sum(x)^2)
        x = list(range(n))  # 0, 1, 2, ..., n-1
        y = prices
        
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi ** 2 for xi in x)
        
        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            return 0.0, 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        
        # Convert to percentage of mean price
        mean_price = sum_y / n if n > 0 else 1
        slope_pct = (slope / mean_price) * 100 if mean_price > 0 else 0.0
        
        return slope, slope_pct
    
    def _analyze_indicators(self, candles: List[Candle], current_price: float) -> IndicatorState:
        """
        Run all indicators and compile their states into a single object.
        
        Args:
            candles: Historical OHLCV data (most recent last)
            current_price: Current market price
            
        Returns:
            IndicatorState with all indicator readings
        """
        state = IndicatorState()
        
        closes = self._extract_closes(candles)
        volumes = self._extract_volumes(candles)
        highs = self._extract_highs(candles)
        lows = self._extract_lows(candles)
        
        # --- EMA Analysis (PRIMARY TRIGGER) ---
        ema_short_values = self.ema_short.calculate(closes)
        ema_long_values = self.ema_long.calculate(closes)
        
        if ema_short_values and ema_long_values and len(ema_short_values) >= 2:
            current_short = ema_short_values[-1]
            current_long = ema_long_values[-1]
            prev_short = ema_short_values[-2]
            prev_long = ema_long_values[-2]
            
            # Current trend
            state.ema_trend_bullish = current_short > current_long
            
            # EMA spread (momentum indicator) - how far apart as percentage
            if current_long > 0:
                state.ema_spread_pct = ((current_short - current_long) / current_long) * 100
            
            # Check for cross on THIS candle (exact moment)
            # Golden cross: short crosses above long
            if prev_short <= prev_long and current_short > current_long:
                state.golden_cross_now = True
            # Death cross: short crosses below long  
            if prev_short >= prev_long and current_short < current_long:
                state.death_cross_now = True
        
        # --- Breakout Analysis (ALTERNATIVE PRIMARY TRIGGER) ---
        if len(highs) > self.BREAKOUT_LOOKBACK + 1:
            # Get recent highs (excluding current candle)
            recent_highs = highs[-(self.BREAKOUT_LOOKBACK + 1):-1]
            recent_high = max(recent_highs)
            
            # Check if current price broke above recent high
            if current_price > recent_high:
                breakout_strength = (current_price - recent_high) / recent_high
                if breakout_strength >= self.BREAKOUT_MIN_STRENGTH:
                    state.breakout_detected = True
                    state.breakout_high = recent_high
                    state.breakout_strength_pct = breakout_strength * 100
        
        # --- Head and Shoulders Analysis ---
        hns_result = self.hns_indicator.detect(highs, lows, closes)
        if hns_result:
            state.inverse_hns_detected = hns_result.get('inverse_pattern', False)
            state.hns_top_detected = hns_result.get('top_pattern', False)
        
        # --- Volume Spike Analysis ---
        volume_result = self.volume_spike_indicator.detect(volumes, closes)
        if volume_result:
            state.volume_spike = volume_result.get('spike_detected', False)
            state.volume_spike_bullish = volume_result.get('bullish_spike', False)
            state.volume_spike_bearish = volume_result.get('bearish_spike', False)
        
        # --- Support/Resistance Analysis ---
        sr_levels = self.sr_indicator.find_levels(highs, lows, closes, current_price)
        if sr_levels:
            state.nearest_support = sr_levels.get('nearest_support')
            state.nearest_resistance = sr_levels.get('nearest_resistance')
            
            # Check if we're near resistance (within 0.5%)
            if state.nearest_resistance and current_price > 0:
                dist_to_resistance = (state.nearest_resistance - current_price) / current_price
                state.near_resistance = dist_to_resistance <= 0.005  # Within 0.5%
        
        # --- RSI / Market Regime Analysis ---
        rsi_result = self.rsi_indicator.get_market_regime(
            closes, 
            bearish_threshold=self.RSI_BEARISH_THRESHOLD,
            bullish_threshold=self.RSI_BULLISH_THRESHOLD
        )
        if rsi_result:
            state.rsi = rsi_result.get('rsi', 50.0)
            state.market_regime = rsi_result.get('regime', 'neutral')
            state.regime_strength = rsi_result.get('strength', 0.0)
            state.is_oversold = rsi_result.get('oversold', False)
            state.is_overbought = rsi_result.get('overbought', False)
        
        # --- Trendline / Linear Regression Analysis ---
        if len(closes) >= self.TRENDLINE_LOOKBACK:
            slope, slope_pct = self._calculate_trendline_slope(closes[-self.TRENDLINE_LOOKBACK:])
            state.trendline_slope = slope
            state.trendline_slope_pct = slope_pct
            state.trendline_bullish = slope > 0
        
        return state
    
    def _calculate_signal_strength(self, state: IndicatorState, is_breakout: bool = False) -> SignalStrength:
        """
        Determine signal strength based on how many confirmations align.
        
        For Golden Cross entries:
            Strong: Golden cross + volume spike + (RSI oversold OR inverse H&S)
            Moderate: Golden cross + volume spike OR favorable RSI
            Weak: Just the golden cross
        
        For Breakout entries:
            Strong: Breakout + volume spike + bullish EMA trend
            Moderate: Breakout + volume spike OR bullish trend
            Weak: Just the breakout
        """
        score = 0
        
        # Breakout entries get bonus for strength of breakout
        if is_breakout:
            if state.breakout_strength_pct >= 0.3:  # Strong breakout (>0.3% above)
                score += 2
            elif state.breakout_strength_pct >= 0.1:  # Moderate breakout
                score += 1
            
            # Breakouts with bullish EMA trend are stronger
            if state.ema_trend_bullish:
                score += 2
        
        # Volume confirmation (applies to both)
        if state.volume_spike_bullish:
            score += 2  # Strong confirmation
        elif state.volume_spike:
            score += 1  # Weak confirmation (any spike)
        
        # RSI favorable (not overbought, bonus if oversold)
        if state.is_oversold:
            score += 2  # Great entry - oversold
        elif not state.is_overbought:
            score += 1  # Room to run
        
        # Pattern confirmation
        if state.inverse_hns_detected:
            score += 2  # Strong reversal pattern
        
        # EMA spread (momentum)
        if state.ema_spread_pct > 0.1:  # Meaningful spread
            score += 1
        
        # Map score to strength
        if score >= 4:
            return SignalStrength.STRONG
        elif score >= 2:
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK
    
    def _calculate_stop_loss(self, current_price: float, state: IndicatorState, 
                             strength: SignalStrength) -> Tuple[float, float]:
        """
        Calculate stop-loss price and percentage.
        
        Base: DEFAULT_STOP_LOSS_PCT * sl_scale
        Then scaled by:
          - Signal strength (stronger = tighter)
          - Trend (with trend = tighter, against = wider)
        
        Returns:
            Tuple of (stop_loss_price, stop_loss_pct)
        """
        # Base SL
        base_sl = self.DEFAULT_STOP_LOSS_PCT * self.sl_scale
        
        # Signal strength scaling
        if strength == SignalStrength.STRONG:
            strength_scale = self.SL_STRENGTH_STRONG
        elif strength == SignalStrength.MODERATE:
            strength_scale = self.SL_STRENGTH_MODERATE
        else:
            strength_scale = self.SL_STRENGTH_WEAK
        
        # Trend scaling (for LONG positions)
        if state.market_regime == 'bullish':
            trend_scale = self.SL_TREND_BULLISH
        elif state.market_regime == 'bearish':
            trend_scale = self.SL_TREND_BEARISH
        else:
            trend_scale = self.SL_TREND_NEUTRAL
        
        # Final SL
        stop_pct = base_sl * strength_scale * trend_scale
        stop_price = current_price * (1 - stop_pct)
        
        return stop_price, stop_pct
    
    def _calculate_take_profit(self, current_price: float, state: IndicatorState,
                               stop_loss_pct: float, strength: SignalStrength) -> Tuple[float, float]:
        """
        Calculate take-profit price and percentage.
        
        Base: DEFAULT_TAKE_PROFIT_PCT * tp_scale
        Then scaled by:
          - Signal strength (stronger = wider, expect bigger move)
          - Trend (with trend = wider, against = tighter)
        
        Returns:
            Tuple of (take_profit_price, take_profit_pct)
        """
        # Base TP
        base_tp = self.DEFAULT_TAKE_PROFIT_PCT * self.tp_scale
        
        # Signal strength scaling
        if strength == SignalStrength.STRONG:
            strength_scale = self.TP_STRENGTH_STRONG
        elif strength == SignalStrength.MODERATE:
            strength_scale = self.TP_STRENGTH_MODERATE
        else:
            strength_scale = self.TP_STRENGTH_WEAK
        
        # Trend scaling (for LONG positions)
        if state.market_regime == 'bullish':
            trend_scale = self.TP_TREND_BULLISH
        elif state.market_regime == 'bearish':
            trend_scale = self.TP_TREND_BEARISH
        else:
            trend_scale = self.TP_TREND_NEUTRAL
        
        # Final TP
        tp_pct = base_tp * strength_scale * trend_scale
        tp_price = current_price * (1 + tp_pct)
        
        return tp_price, tp_pct
    
    def _calculate_position_size_pct(self, strength: SignalStrength) -> float:
        """
        Determine position size as percentage of capital based on signal strength.
        """
        if strength == SignalStrength.STRONG:
            return 1.0   # Full allocation
        elif strength == SignalStrength.MODERATE:
            return 0.7   # 70% allocation
        else:
            return 0.4   # 40% allocation for weak signals
    
    def should_enter(self, candles: List[Candle], current_price: float) -> Optional[EntrySignal]:
        """
        Generate an entry signal based on EMA crossover with confirmations.
        
        Entry Conditions for LONG:
            PRIMARY TRIGGER (required):
                - Golden cross: Short EMA crosses ABOVE Long EMA THIS candle
            
            CONFIRMATIONS (improve signal strength):
                - Volume spike (especially bullish)
                - RSI not overbought (room to run)
                - Inverse Head and Shoulders pattern
                - Bullish EMA trend (for breakouts)
            
            REJECTIONS (block entry):
                - RSI overbought (>70)
                - Price at resistance (for golden cross only)
        
        Returns:
            EntrySignal if conditions met, None otherwise
        """
        # Validate minimum data
        if len(candles) < self.MIN_CANDLES:
            return None
        
        # Analyze all indicators
        state = self._analyze_indicators(candles, current_price)
        
        # --- PRIMARY TRIGGERS: Golden Cross OR Breakout ---
        is_golden_cross = state.golden_cross_now
        is_breakout = state.breakout_detected
        
        if not is_golden_cross and not is_breakout:
            return None  # Must have either trigger
        
        # --- REJECTIONS: Block entry ---
        
        # Rejection 1: RSI overbought - no room to run (applies to both)
        if state.is_overbought:
            return None
        
        # Rejection 2: Price right at resistance (only for golden cross, not breakouts)
        # Breakouts by definition are breaking resistance, so don't reject
        if is_golden_cross and not is_breakout and state.near_resistance:
            return None
        
        # Rejection 3: Negative trendline slope - don't enter against the trend
        if self.TRENDLINE_REJECT_NEGATIVE and not state.trendline_bullish:
            return None
        
        # --- GENERATE SIGNAL ---
        # We have a valid trigger and no rejections - generate signal
        
        # Calculate signal strength based on confirmations
        strength = self._calculate_signal_strength(state, is_breakout=is_breakout)
        
        # Calculate risk management levels
        stop_price, stop_pct = self._calculate_stop_loss(current_price, state, strength)
        tp_price, tp_pct = self._calculate_take_profit(current_price, state, stop_pct, strength)
        
        # Determine position size
        size_pct = self._calculate_position_size_pct(strength)
        
        # Build reason string for logging
        reasons = []
        if is_breakout:
            reasons.append(f"Breakout(+{state.breakout_strength_pct:.2f}%)")
        if is_golden_cross:
            reasons.append("Golden Cross")
        if state.inverse_hns_detected:
            reasons.append("Inv H&S")
        if state.volume_spike_bullish:
            reasons.append("bullish vol")
        elif state.volume_spike:
            reasons.append("vol spike")
        if state.is_oversold:
            reasons.append("oversold")
        if is_breakout and state.ema_trend_bullish:
            reasons.append("EMA bullish")
        
        # Include market regime in reason
        regime_str = f"RSI:{state.rsi:.0f}({state.market_regime})"
        reason = f"LONG: {', '.join(reasons)} | {regime_str} | SL:{stop_pct:.2%} TP:{tp_pct:.2%}"
        
        # Use trailing stop for breakouts or strong signals
        use_trailing = is_breakout or strength == SignalStrength.STRONG
        
        return EntrySignal(
            side=PositionSide.LONG,
            strength=strength,
            entry_price=None,  # Market order
            stop_loss_pct=stop_pct,
            take_profit_pct=tp_pct,
            use_trailing_stop=use_trailing,
            size_pct=size_pct,
            reason=reason
        )
    
    def should_exit_early(self, candles: List[Candle], current_price: float,
                          entry_price: float, side: PositionSide) -> bool:
        """
        Determine if an early exit is warranted based on indicator signals.
        
        Exit Conditions for LONG position:
            PRIMARY EXIT SIGNAL:
                - Death cross (short EMA crosses below long EMA)
            
            ADDITIONAL EXIT SIGNALS:
                - Head and Shoulders top pattern detected
                - RSI overbought + volume spike (distribution)
            
            Single signal is enough to exit - better safe than sorry.
        
        Args:
            candles: Historical OHLCV data
            current_price: Current market price
            entry_price: Position entry price
            side: Position side (LONG/SHORT)
            
        Returns:
            True to exit, False to hold
        """
        # Only handle LONG positions for now
        if side != PositionSide.LONG:
            return False
        
        # Need minimum data
        if len(candles) < self.MIN_CANDLES:
            return False
        
        # Analyze indicators
        state = self._analyze_indicators(candles, current_price)
        
        # --- PRIMARY EXIT: Death Cross ---
        if state.death_cross_now:
            return True
        
        # --- PATTERN EXIT: Head and Shoulders Top ---
        if state.hns_top_detected:
            return True
        
        # --- DISTRIBUTION EXIT: Overbought + Volume Spike ---
        # When RSI is overbought and we get a volume spike, 
        # it often signals distribution (smart money selling)
        if state.is_overbought and state.volume_spike:
            return True
        
        # --- MOMENTUM LOSS: EMA spread narrowing significantly ---
        # If we had positive spread and it's now minimal, momentum is dying
        if state.ema_trend_bullish and state.ema_spread_pct < 0.02:
            # We're barely bullish - check if we're profitable
            pnl_pct = (current_price - entry_price) / entry_price
            if pnl_pct > 0.003:  # At least 0.3% profit - lock it in
                return True
        
        return False
    
    def get_name(self) -> str:
        """Return strategy name for logging."""
        return self.name
    
    def get_indicator_summary(self, candles: List[Candle], current_price: float) -> Dict:
        """
        Get a summary of all indicator states for debugging/display.
        
        Args:
            candles: Historical OHLCV data
            current_price: Current market price
            
        Returns:
            Dictionary with all indicator readings
        """
        if len(candles) < self.MIN_CANDLES:
            return {"error": f"Insufficient data (need {self.MIN_CANDLES} candles)"}
        
        state = self._analyze_indicators(candles, current_price)
        
        return {
            "ema": {
                "trend_bullish": state.ema_trend_bullish,
                "golden_cross_now": state.golden_cross_now,
                "death_cross_now": state.death_cross_now,
                "spread_pct": state.ema_spread_pct
            },
            "patterns": {
                "inverse_hns": state.inverse_hns_detected,
                "hns_top": state.hns_top_detected
            },
            "volume": {
                "spike": state.volume_spike,
                "bullish_spike": state.volume_spike_bullish,
                "bearish_spike": state.volume_spike_bearish
            },
            "levels": {
                "support": state.nearest_support,
                "resistance": state.nearest_resistance,
                "near_resistance": state.near_resistance
            },
            "market_regime": {
                "rsi": state.rsi,
                "regime": state.market_regime,
                "strength": state.regime_strength,
                "oversold": state.is_oversold,
                "overbought": state.is_overbought
            }
        }
