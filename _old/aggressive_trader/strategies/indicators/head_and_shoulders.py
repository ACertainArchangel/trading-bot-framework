"""
Head and Shoulders Pattern Detection.

On a 1-minute timeframe, H&S patterns form quickly but are also noisy.
This implementation uses swing point detection with tolerance-based matching.

Patterns detected:
- Head and Shoulders Top (bearish reversal): Three peaks, middle one highest
- Inverse Head and Shoulders (bullish reversal): Three troughs, middle one lowest

Key considerations for 1m timeframe:
- Use percentage-based tolerance for shoulder comparison (not exact matching)
- Require minimum pattern width to filter noise
- Neckline break confirmation is crucial
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass 
class HnSPattern:
    """Represents a detected Head and Shoulders pattern."""
    pattern_type: str           # 'top' or 'inverse'
    left_shoulder: float        # Price of left shoulder
    head: float                 # Price of head
    right_shoulder: float       # Price of right shoulder
    neckline: float            # Neckline price level
    left_shoulder_idx: int      # Index of left shoulder
    head_idx: int              # Index of head
    right_shoulder_idx: int    # Index of right shoulder
    confidence: float          # 0-1 confidence score


class HeadAndShouldersIndicator:
    """
    Detects Head and Shoulders patterns (both top and inverse).
    
    Optimized for 1-minute timeframe with noise tolerance.
    """
    
    def __init__(self, swing_lookback: int = 3, shoulder_tolerance_pct: float = 1.5,
                 min_pattern_bars: int = 10, max_pattern_bars: int = 60,
                 neckline_break_pct: float = 0.1):
        """
        Initialize H&S detector.
        
        Args:
            swing_lookback: Bars on each side to confirm swing point (default 3)
            shoulder_tolerance_pct: Max % difference between shoulders (default 1.5%)
            min_pattern_bars: Minimum pattern width in bars (default 10 = 10 mins)
            max_pattern_bars: Maximum pattern width in bars (default 60 = 1 hour)
            neckline_break_pct: % below/above neckline to confirm break (default 0.1%)
        """
        self.swing_lookback = swing_lookback
        self.shoulder_tolerance_pct = shoulder_tolerance_pct
        self.min_pattern_bars = min_pattern_bars
        self.max_pattern_bars = max_pattern_bars
        self.neckline_break_pct = neckline_break_pct
    
    def _find_swing_highs(self, highs: List[float]) -> List[Tuple[int, float]]:
        """Find swing high points (local maxima)."""
        swing_highs = []
        n = len(highs)
        
        for i in range(self.swing_lookback, n - self.swing_lookback):
            is_swing = True
            current_high = highs[i]
            
            for j in range(1, self.swing_lookback + 1):
                if highs[i - j] >= current_high or highs[i + j] >= current_high:
                    is_swing = False
                    break
            
            if is_swing:
                swing_highs.append((i, current_high))
        
        return swing_highs
    
    def _find_swing_lows(self, lows: List[float]) -> List[Tuple[int, float]]:
        """Find swing low points (local minima)."""
        swing_lows = []
        n = len(lows)
        
        for i in range(self.swing_lookback, n - self.swing_lookback):
            is_swing = True
            current_low = lows[i]
            
            for j in range(1, self.swing_lookback + 1):
                if lows[i - j] <= current_low or lows[i + j] <= current_low:
                    is_swing = False
                    break
            
            if is_swing:
                swing_lows.append((i, current_low))
        
        return swing_lows
    
    def _shoulders_match(self, left: float, right: float) -> bool:
        """Check if two shoulders are approximately equal within tolerance."""
        if left == 0:
            return False
        diff_pct = abs(left - right) / left * 100
        return diff_pct <= self.shoulder_tolerance_pct
    
    def _calculate_confidence(self, left_shoulder: float, head: float, 
                             right_shoulder: float, pattern_type: str) -> float:
        """
        Calculate confidence score for the pattern.
        
        Higher confidence when:
        - Shoulders are more equal
        - Head is significantly different from shoulders
        - Pattern proportions are balanced
        """
        # Shoulder symmetry (0-0.4 points)
        shoulder_diff_pct = abs(left_shoulder - right_shoulder) / left_shoulder * 100
        shoulder_score = max(0, 0.4 * (1 - shoulder_diff_pct / self.shoulder_tolerance_pct))
        
        # Head prominence (0-0.4 points)
        avg_shoulder = (left_shoulder + right_shoulder) / 2
        if pattern_type == 'top':
            head_diff_pct = (head - avg_shoulder) / avg_shoulder * 100
        else:
            head_diff_pct = (avg_shoulder - head) / avg_shoulder * 100
        
        # Head should be at least 0.5% different, up to 3% for max score
        head_score = min(0.4, max(0, 0.4 * (head_diff_pct - 0.5) / 2.5))
        
        # Base confidence
        base_confidence = 0.2
        
        return min(1.0, base_confidence + shoulder_score + head_score)
    
    def _detect_top_pattern(self, swing_highs: List[Tuple[int, float]], 
                           swing_lows: List[Tuple[int, float]],
                           closes: List[float]) -> Optional[HnSPattern]:
        """
        Detect Head and Shoulders Top pattern (bearish).
        
        Pattern structure:
        - Left shoulder (high)
        - Head (higher high)
        - Right shoulder (high, ~equal to left)
        - Neckline connecting the lows between shoulders
        """
        if len(swing_highs) < 3:
            return None
        
        # Look for pattern in recent swing highs
        # Start from most recent and work backwards
        for i in range(len(swing_highs) - 1, 1, -1):
            right_idx, right_shoulder = swing_highs[i]
            
            # Look for head (higher than right shoulder)
            for j in range(i - 1, 0, -1):
                head_idx, head = swing_highs[j]
                
                # Head must be higher than right shoulder
                if head <= right_shoulder:
                    continue
                
                # Check pattern width
                pattern_width = right_idx - head_idx
                if pattern_width < self.min_pattern_bars // 2:
                    continue
                
                # Look for left shoulder
                for k in range(j - 1, -1, -1):
                    left_idx, left_shoulder = swing_highs[k]
                    
                    # Left shoulder must be lower than head
                    if left_shoulder >= head:
                        continue
                    
                    # Check total pattern width
                    total_width = right_idx - left_idx
                    if total_width < self.min_pattern_bars or total_width > self.max_pattern_bars:
                        continue
                    
                    # Check shoulder symmetry
                    if not self._shoulders_match(left_shoulder, right_shoulder):
                        continue
                    
                    # Find neckline (lows between shoulders and head)
                    neckline_lows = [
                        low for idx, low in swing_lows 
                        if left_idx < idx < right_idx
                    ]
                    
                    if not neckline_lows:
                        # Use simple low in the range
                        neckline = min(closes[left_idx:right_idx+1])
                    else:
                        neckline = sum(neckline_lows) / len(neckline_lows)
                    
                    # Check if current price is breaking neckline
                    current_price = closes[-1]
                    neckline_break_threshold = neckline * (1 - self.neckline_break_pct / 100)
                    
                    # Pattern is forming or confirmed
                    confidence = self._calculate_confidence(
                        left_shoulder, head, right_shoulder, 'top'
                    )
                    
                    # Boost confidence if neckline is broken
                    if current_price < neckline_break_threshold:
                        confidence = min(1.0, confidence + 0.2)
                    
                    return HnSPattern(
                        pattern_type='top',
                        left_shoulder=left_shoulder,
                        head=head,
                        right_shoulder=right_shoulder,
                        neckline=neckline,
                        left_shoulder_idx=left_idx,
                        head_idx=head_idx,
                        right_shoulder_idx=right_idx,
                        confidence=confidence
                    )
        
        return None
    
    def _detect_inverse_pattern(self, swing_highs: List[Tuple[int, float]], 
                                swing_lows: List[Tuple[int, float]],
                                closes: List[float]) -> Optional[HnSPattern]:
        """
        Detect Inverse Head and Shoulders pattern (bullish).
        
        Pattern structure:
        - Left shoulder (low)
        - Head (lower low)
        - Right shoulder (low, ~equal to left)
        - Neckline connecting the highs between shoulders
        """
        if len(swing_lows) < 3:
            return None
        
        # Look for pattern in recent swing lows
        for i in range(len(swing_lows) - 1, 1, -1):
            right_idx, right_shoulder = swing_lows[i]
            
            # Look for head (lower than right shoulder)
            for j in range(i - 1, 0, -1):
                head_idx, head = swing_lows[j]
                
                # Head must be lower than right shoulder
                if head >= right_shoulder:
                    continue
                
                # Check pattern width
                pattern_width = right_idx - head_idx
                if pattern_width < self.min_pattern_bars // 2:
                    continue
                
                # Look for left shoulder
                for k in range(j - 1, -1, -1):
                    left_idx, left_shoulder = swing_lows[k]
                    
                    # Left shoulder must be higher than head
                    if left_shoulder <= head:
                        continue
                    
                    # Check total pattern width
                    total_width = right_idx - left_idx
                    if total_width < self.min_pattern_bars or total_width > self.max_pattern_bars:
                        continue
                    
                    # Check shoulder symmetry
                    if not self._shoulders_match(left_shoulder, right_shoulder):
                        continue
                    
                    # Find neckline (highs between shoulders and head)
                    neckline_highs = [
                        high for idx, high in swing_highs 
                        if left_idx < idx < right_idx
                    ]
                    
                    if not neckline_highs:
                        # Use simple high in the range
                        neckline = max(closes[left_idx:right_idx+1])
                    else:
                        neckline = sum(neckline_highs) / len(neckline_highs)
                    
                    # Check if current price is breaking neckline
                    current_price = closes[-1]
                    neckline_break_threshold = neckline * (1 + self.neckline_break_pct / 100)
                    
                    # Pattern is forming or confirmed
                    confidence = self._calculate_confidence(
                        left_shoulder, head, right_shoulder, 'inverse'
                    )
                    
                    # Boost confidence if neckline is broken
                    if current_price > neckline_break_threshold:
                        confidence = min(1.0, confidence + 0.2)
                    
                    return HnSPattern(
                        pattern_type='inverse',
                        left_shoulder=left_shoulder,
                        head=head,
                        right_shoulder=right_shoulder,
                        neckline=neckline,
                        left_shoulder_idx=left_idx,
                        head_idx=head_idx,
                        right_shoulder_idx=right_idx,
                        confidence=confidence
                    )
        
        return None
    
    def detect(self, highs: List[float], lows: List[float], 
               closes: List[float]) -> Optional[Dict]:
        """
        Detect Head and Shoulders patterns in price data.
        
        Args:
            highs: List of high prices (most recent last)
            lows: List of low prices (most recent last)
            closes: List of closing prices (most recent last)
            
        Returns:
            Dictionary with:
                - 'top_pattern': True if H&S top detected (bearish)
                - 'inverse_pattern': True if inverse H&S detected (bullish)
                - 'pattern_details': HnSPattern object if pattern found
                - 'neckline': Neckline price if pattern found
                - 'confidence': Pattern confidence score (0-1)
            Returns None if insufficient data
        """
        min_required = self.max_pattern_bars + self.swing_lookback * 2
        if len(highs) < min_required:
            return None
        
        # Find swing points
        swing_highs = self._find_swing_highs(highs)
        swing_lows = self._find_swing_lows(lows)
        
        # Try to detect both patterns
        top_pattern = self._detect_top_pattern(swing_highs, swing_lows, closes)
        inverse_pattern = self._detect_inverse_pattern(swing_highs, swing_lows, closes)
        
        # Determine which pattern (if any) to return
        # Prefer higher confidence if both detected
        active_pattern = None
        if top_pattern and inverse_pattern:
            active_pattern = top_pattern if top_pattern.confidence >= inverse_pattern.confidence else inverse_pattern
        elif top_pattern:
            active_pattern = top_pattern
        elif inverse_pattern:
            active_pattern = inverse_pattern
        
        result = {
            'top_pattern': top_pattern is not None and (active_pattern == top_pattern if active_pattern else False),
            'inverse_pattern': inverse_pattern is not None and (active_pattern == inverse_pattern if active_pattern else False),
            'pattern_details': None,
            'neckline': None,
            'confidence': 0.0
        }
        
        if active_pattern:
            result['pattern_details'] = {
                'type': active_pattern.pattern_type,
                'left_shoulder': active_pattern.left_shoulder,
                'head': active_pattern.head,
                'right_shoulder': active_pattern.right_shoulder,
                'neckline': active_pattern.neckline,
                'left_idx': active_pattern.left_shoulder_idx,
                'head_idx': active_pattern.head_idx,
                'right_idx': active_pattern.right_shoulder_idx
            }
            result['neckline'] = active_pattern.neckline
            result['confidence'] = active_pattern.confidence
        
        return result
    
    def get_target_price(self, pattern: Dict, current_price: float) -> Optional[float]:
        """
        Calculate price target based on H&S pattern.
        
        Traditional target = neckline +/- (head to neckline distance)
        
        Args:
            pattern: Pattern dict from detect()
            current_price: Current market price
            
        Returns:
            Target price or None if no valid pattern
        """
        if not pattern or not pattern.get('pattern_details'):
            return None
        
        details = pattern['pattern_details']
        neckline = details['neckline']
        head = details['head']
        
        # Calculate pattern height
        pattern_height = abs(head - neckline)
        
        if details['type'] == 'top':
            # Bearish target: neckline - pattern height
            target = neckline - pattern_height
        else:
            # Bullish target: neckline + pattern height
            target = neckline + pattern_height
        
        return target
