"""
Relative Strength Index (RSI) Indicator.

RSI measures the speed and magnitude of recent price changes to evaluate
overbought or oversold conditions.

RSI ranges from 0 to 100:
- Above 70: Overbought (potential reversal down)
- Below 30: Oversold (potential reversal up)
- 50: Neutral

For market regime detection:
- RSI < 40: Bearish regime (lower momentum)
- RSI 40-60: Neutral regime
- RSI > 60: Bullish regime (stronger momentum)
"""

from typing import List, Optional, Dict


class RSIIndicator:
    """
    RSI calculator with market regime detection.
    """
    
    def __init__(self, period: int = 14):
        """
        Initialize RSI with specified period.
        
        Args:
            period: Lookback period for RSI calculation (default 14)
        """
        self.period = period
    
    def calculate(self, closes: List[float]) -> Optional[float]:
        """
        Calculate current RSI value.
        
        Args:
            closes: List of closing prices (most recent last)
            
        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(closes) < self.period + 1:
            return None
        
        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Use only the most recent 'period' changes for initial calculation
        recent_changes = changes[-(self.period):]
        
        # Separate gains and losses
        gains = [max(0, c) for c in recent_changes]
        losses = [abs(min(0, c)) for c in recent_changes]
        
        # Calculate average gain and loss (Wilder's smoothing - SMA for first calc)
        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period
        
        if avg_loss == 0:
            return 100.0  # No losses = maximum strength
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_smoothed(self, closes: List[float]) -> Optional[float]:
        """
        Calculate RSI using Wilder's smoothing method (more accurate).
        
        This is the traditional RSI calculation that uses exponential
        smoothing after the initial SMA period.
        
        Args:
            closes: List of closing prices (most recent last)
            
        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(closes) < self.period + 1:
            return None
        
        # Calculate all price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Initial averages using SMA
        initial_gains = [max(0, c) for c in changes[:self.period]]
        initial_losses = [abs(min(0, c)) for c in changes[:self.period]]
        
        avg_gain = sum(initial_gains) / self.period
        avg_loss = sum(initial_losses) / self.period
        
        # Apply Wilder's smoothing for remaining periods
        for change in changes[self.period:]:
            gain = max(0, change)
            loss = abs(min(0, change))
            
            avg_gain = (avg_gain * (self.period - 1) + gain) / self.period
            avg_loss = (avg_loss * (self.period - 1) + loss) / self.period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def get_all_values(self, closes: List[float]) -> Optional[List[float]]:
        """
        Calculate RSI for all valid periods.
        
        Args:
            closes: List of closing prices
            
        Returns:
            List of RSI values, or None if insufficient data
        """
        if len(closes) < self.period + 1:
            return None
        
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Initial averages
        initial_gains = [max(0, c) for c in changes[:self.period]]
        initial_losses = [abs(min(0, c)) for c in changes[:self.period]]
        
        avg_gain = sum(initial_gains) / self.period
        avg_loss = sum(initial_losses) / self.period
        
        rsi_values = []
        
        # First RSI value
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
        
        # Subsequent values with smoothing
        for change in changes[self.period:]:
            gain = max(0, change)
            loss = abs(min(0, change))
            
            avg_gain = (avg_gain * (self.period - 1) + gain) / self.period
            avg_loss = (avg_loss * (self.period - 1) + loss) / self.period
            
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
        
        return rsi_values
    
    def get_market_regime(self, closes: List[float], 
                          bearish_threshold: float = 40,
                          bullish_threshold: float = 60) -> Optional[Dict]:
        """
        Determine market regime based on RSI.
        
        Args:
            closes: List of closing prices
            bearish_threshold: RSI below this = bearish (default 40)
            bullish_threshold: RSI above this = bullish (default 60)
            
        Returns:
            Dictionary with:
                - 'rsi': Current RSI value
                - 'regime': 'bearish', 'neutral', or 'bullish'
                - 'strength': 0-1 score of regime strength
                - 'oversold': True if RSI < 30
                - 'overbought': True if RSI > 70
        """
        rsi = self.calculate_smoothed(closes)
        if rsi is None:
            return None
        
        # Determine regime
        if rsi < bearish_threshold:
            regime = 'bearish'
            # Strength increases as RSI gets lower
            strength = (bearish_threshold - rsi) / bearish_threshold
        elif rsi > bullish_threshold:
            regime = 'bullish'
            # Strength increases as RSI gets higher
            strength = (rsi - bullish_threshold) / (100 - bullish_threshold)
        else:
            regime = 'neutral'
            # Strength is how close to 50 (center)
            distance_from_center = abs(rsi - 50)
            strength = 1 - (distance_from_center / 10)  # Max strength at RSI=50
        
        strength = max(0, min(1, strength))  # Clamp to 0-1
        
        return {
            'rsi': rsi,
            'regime': regime,
            'strength': strength,
            'oversold': rsi < 30,
            'overbought': rsi > 70
        }
    
    def is_oversold(self, closes: List[float], threshold: float = 30) -> Optional[bool]:
        """Check if market is oversold."""
        rsi = self.calculate_smoothed(closes)
        return rsi < threshold if rsi is not None else None
    
    def is_overbought(self, closes: List[float], threshold: float = 70) -> Optional[bool]:
        """Check if market is overbought."""
        rsi = self.calculate_smoothed(closes)
        return rsi > threshold if rsi is not None else None
    
    def get_divergence(self, closes: List[float], lookback: int = 10) -> Optional[Dict]:
        """
        Detect RSI divergence from price (advanced signal).
        
        Bullish divergence: Price makes lower low, RSI makes higher low
        Bearish divergence: Price makes higher high, RSI makes lower high
        
        Args:
            closes: List of closing prices
            lookback: Periods to check for divergence
            
        Returns:
            Dictionary with divergence info or None
        """
        rsi_values = self.get_all_values(closes)
        if not rsi_values or len(rsi_values) < lookback:
            return None
        
        recent_closes = closes[-lookback:]
        recent_rsi = rsi_values[-lookback:]
        
        # Find price extremes
        price_low_idx = recent_closes.index(min(recent_closes))
        price_high_idx = recent_closes.index(max(recent_closes))
        
        # Check for bullish divergence (price lower low, RSI higher low)
        # Compare current low region vs earlier low region
        mid = lookback // 2
        early_price_low = min(recent_closes[:mid])
        late_price_low = min(recent_closes[mid:])
        early_rsi_at_low = recent_rsi[recent_closes[:mid].index(early_price_low)]
        late_rsi_at_low = recent_rsi[mid + recent_closes[mid:].index(late_price_low)]
        
        bullish_divergence = late_price_low < early_price_low and late_rsi_at_low > early_rsi_at_low
        
        # Check for bearish divergence (price higher high, RSI lower high)
        early_price_high = max(recent_closes[:mid])
        late_price_high = max(recent_closes[mid:])
        early_rsi_at_high = recent_rsi[recent_closes[:mid].index(early_price_high)]
        late_rsi_at_high = recent_rsi[mid + recent_closes[mid:].index(late_price_high)]
        
        bearish_divergence = late_price_high > early_price_high and late_rsi_at_high < early_rsi_at_high
        
        return {
            'bullish_divergence': bullish_divergence,
            'bearish_divergence': bearish_divergence,
            'current_rsi': rsi_values[-1]
        }
