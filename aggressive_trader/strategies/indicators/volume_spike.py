"""
Volume Spike Indicator.

Detects unusual volume activity that often precedes or confirms significant price moves.
A volume spike is typically defined as volume exceeding N standard deviations above
the moving average, or simply X times the average volume.

Bullish spike: High volume + price increase
Bearish spike: High volume + price decrease
"""

from typing import List, Dict, Optional
import math


class VolumeSpikeIndicator:
    """
    Volume spike detection with directional analysis.
    """
    
    def __init__(self, threshold: float = 2.0, lookback: int = 20, 
                 use_std_dev: bool = False, std_dev_multiplier: float = 2.0):
        """
        Initialize volume spike detector.
        
        Args:
            threshold: Multiplier above average volume for spike detection (default 2.0x)
            lookback: Number of periods for average volume calculation (default 20)
            use_std_dev: If True, use standard deviation method instead of simple multiplier
            std_dev_multiplier: Number of std devs above mean for spike (if use_std_dev=True)
        """
        self.threshold = threshold
        self.lookback = lookback
        self.use_std_dev = use_std_dev
        self.std_dev_multiplier = std_dev_multiplier
    
    def _calculate_average(self, values: List[float]) -> float:
        """Calculate simple average of values."""
        if not values:
            return 0.0
        return sum(values) / len(values)
    
    def _calculate_std_dev(self, values: List[float], mean: float) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    def detect(self, volumes: List[float], closes: List[float]) -> Optional[Dict]:
        """
        Detect volume spikes and determine their direction.
        
        Args:
            volumes: List of volume data (most recent last)
            closes: List of closing prices (most recent last)
            
        Returns:
            Dictionary with:
                - 'spike_detected': True if current volume is a spike
                - 'bullish_spike': True if spike with price increase
                - 'bearish_spike': True if spike with price decrease
                - 'volume_ratio': Current volume / average volume
                - 'avg_volume': Average volume over lookback period
                - 'current_volume': Most recent volume
            Returns None if insufficient data
        """
        if len(volumes) < self.lookback + 1 or len(closes) < 2:
            return None
        
        # Calculate average volume (excluding current candle)
        lookback_volumes = volumes[-(self.lookback + 1):-1]
        avg_volume = self._calculate_average(lookback_volumes)
        
        if avg_volume == 0:
            return None
        
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume
        
        # Determine if spike
        if self.use_std_dev:
            std_dev = self._calculate_std_dev(lookback_volumes, avg_volume)
            spike_threshold = avg_volume + (std_dev * self.std_dev_multiplier)
            spike_detected = current_volume > spike_threshold
        else:
            spike_detected = volume_ratio >= self.threshold
        
        # Determine direction based on price change
        price_change = closes[-1] - closes[-2]
        price_change_pct = price_change / closes[-2] if closes[-2] != 0 else 0
        
        bullish_spike = spike_detected and price_change > 0
        bearish_spike = spike_detected and price_change < 0
        
        return {
            'spike_detected': spike_detected,
            'bullish_spike': bullish_spike,
            'bearish_spike': bearish_spike,
            'volume_ratio': volume_ratio,
            'avg_volume': avg_volume,
            'current_volume': current_volume,
            'price_change_pct': price_change_pct
        }
    
    def get_volume_trend(self, volumes: List[float], periods: int = 5) -> Optional[str]:
        """
        Analyze recent volume trend.
        
        Args:
            volumes: List of volume data
            periods: Number of recent periods to analyze
            
        Returns:
            'increasing', 'decreasing', or 'stable'
            None if insufficient data
        """
        if len(volumes) < periods + self.lookback:
            return None
        
        recent_volumes = volumes[-periods:]
        
        # Calculate trend using linear regression slope
        n = len(recent_volumes)
        sum_x = sum(range(n))
        sum_y = sum(recent_volumes)
        sum_xy = sum(i * v for i, v in enumerate(recent_volumes))
        sum_x2 = sum(i ** 2 for i in range(n))
        
        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            return 'stable'
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        
        # Normalize slope relative to average volume
        avg_recent = self._calculate_average(recent_volumes)
        if avg_recent == 0:
            return 'stable'
        
        normalized_slope = slope / avg_recent
        
        # Threshold for trend detection
        if normalized_slope > 0.1:
            return 'increasing'
        elif normalized_slope < -0.1:
            return 'decreasing'
        else:
            return 'stable'
    
    def detect_climax(self, volumes: List[float], closes: List[float], 
                      climax_threshold: float = 3.0) -> Optional[Dict]:
        """
        Detect potential climax volume (exhaustion moves).
        
        Climax volume often signals the end of a trend - extremely high volume
        with a significant price move that may indicate exhaustion.
        
        Args:
            volumes: List of volume data
            closes: List of closing prices
            climax_threshold: Multiplier for climax detection (higher than regular spike)
            
        Returns:
            Dictionary with climax information or None
        """
        result = self.detect(volumes, closes)
        if not result:
            return None
        
        is_climax = result['volume_ratio'] >= climax_threshold
        
        if not is_climax:
            return {
                'climax_detected': False,
                'climax_type': None
            }
        
        # Determine climax type
        if result['bullish_spike']:
            climax_type = 'buying_climax'  # Potential top
        elif result['bearish_spike']:
            climax_type = 'selling_climax'  # Potential bottom
        else:
            climax_type = 'neutral_climax'
        
        return {
            'climax_detected': True,
            'climax_type': climax_type,
            'volume_ratio': result['volume_ratio'],
            'price_change_pct': result['price_change_pct']
        }
