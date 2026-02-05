"""
Support and Resistance Level Detection.

On a 1-minute timeframe, S/R levels are detected by finding price zones where:
1. Price has reversed multiple times (swing highs/lows cluster)
2. High volume occurred (indicating significant trading interest)

Levels are treated as ZONES rather than exact prices to handle noise.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PriceLevel:
    """Represents a support or resistance zone."""
    price: float           # Center price of the zone
    strength: int          # Number of touches/bounces
    level_type: str        # 'support' or 'resistance'
    zone_width: float      # Width of the zone as percentage


class SupportResistanceIndicator:
    """
    Identifies support and resistance zones from price action.
    
    Optimized for 1-minute timeframe with noise filtering.
    """
    
    def __init__(self, lookback: int = 50, zone_threshold_pct: float = 0.15,
                 min_touches: int = 2, swing_lookback: int = 3):
        """
        Initialize S/R detector.
        
        Args:
            lookback: Number of candles to analyze (default 50 for 1m = ~1 hour)
            zone_threshold_pct: Price range to consider same zone (0.15 = 0.15%)
            min_touches: Minimum touches to confirm a level (default 2)
            swing_lookback: Candles on each side to confirm swing point (default 3)
        """
        self.lookback = lookback
        self.zone_threshold_pct = zone_threshold_pct
        self.min_touches = min_touches
        self.swing_lookback = swing_lookback
    
    def _find_swing_highs(self, highs: List[float], closes: List[float]) -> List[Tuple[int, float]]:
        """
        Find swing high points (local maxima).
        
        A swing high is a high that is higher than `swing_lookback` candles on each side.
        
        Returns:
            List of (index, price) tuples for swing highs
        """
        swing_highs = []
        n = len(highs)
        
        for i in range(self.swing_lookback, n - self.swing_lookback):
            is_swing = True
            current_high = highs[i]
            
            # Check left side
            for j in range(1, self.swing_lookback + 1):
                if highs[i - j] >= current_high:
                    is_swing = False
                    break
            
            # Check right side
            if is_swing:
                for j in range(1, self.swing_lookback + 1):
                    if highs[i + j] >= current_high:
                        is_swing = False
                        break
            
            if is_swing:
                swing_highs.append((i, current_high))
        
        return swing_highs
    
    def _find_swing_lows(self, lows: List[float], closes: List[float]) -> List[Tuple[int, float]]:
        """
        Find swing low points (local minima).
        
        A swing low is a low that is lower than `swing_lookback` candles on each side.
        
        Returns:
            List of (index, price) tuples for swing lows
        """
        swing_lows = []
        n = len(lows)
        
        for i in range(self.swing_lookback, n - self.swing_lookback):
            is_swing = True
            current_low = lows[i]
            
            # Check left side
            for j in range(1, self.swing_lookback + 1):
                if lows[i - j] <= current_low:
                    is_swing = False
                    break
            
            # Check right side
            if is_swing:
                for j in range(1, self.swing_lookback + 1):
                    if lows[i + j] <= current_low:
                        is_swing = False
                        break
            
            if is_swing:
                swing_lows.append((i, current_low))
        
        return swing_lows
    
    def _cluster_levels(self, points: List[Tuple[int, float]], 
                        reference_price: float) -> List[PriceLevel]:
        """
        Cluster nearby swing points into zones.
        
        Args:
            points: List of (index, price) swing points
            reference_price: Current price for calculating zone threshold
            
        Returns:
            List of PriceLevel objects representing clustered zones
        """
        if not points:
            return []
        
        # Sort by price
        sorted_points = sorted(points, key=lambda x: x[1])
        
        # Calculate absolute threshold from percentage
        threshold = reference_price * (self.zone_threshold_pct / 100)
        
        clusters = []
        current_cluster = [sorted_points[0]]
        
        for i in range(1, len(sorted_points)):
            price = sorted_points[i][1]
            cluster_avg = sum(p[1] for p in current_cluster) / len(current_cluster)
            
            if abs(price - cluster_avg) <= threshold:
                # Add to current cluster
                current_cluster.append(sorted_points[i])
            else:
                # Save current cluster and start new one
                if len(current_cluster) >= self.min_touches:
                    clusters.append(current_cluster)
                current_cluster = [sorted_points[i]]
        
        # Don't forget last cluster
        if len(current_cluster) >= self.min_touches:
            clusters.append(current_cluster)
        
        # Convert clusters to PriceLevel objects
        levels = []
        for cluster in clusters:
            prices = [p[1] for p in cluster]
            avg_price = sum(prices) / len(prices)
            zone_width = (max(prices) - min(prices)) / avg_price if avg_price > 0 else 0
            
            levels.append(PriceLevel(
                price=avg_price,
                strength=len(cluster),
                level_type='unknown',  # Will be set by caller
                zone_width=zone_width
            ))
        
        return levels
    
    def find_levels(self, highs: List[float], lows: List[float], 
                    closes: List[float], current_price: float) -> Optional[Dict]:
        """
        Find support and resistance levels relative to current price.
        
        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            current_price: Current market price
            
        Returns:
            Dictionary with:
                - 'supports': List of support levels below current price
                - 'resistances': List of resistance levels above current price
                - 'nearest_support': Closest support price (or None)
                - 'nearest_resistance': Closest resistance price (or None)
                - 'support_zone': (low, high) of nearest support zone
                - 'resistance_zone': (low, high) of nearest resistance zone
            Returns None if insufficient data
        """
        min_required = self.lookback + self.swing_lookback
        if len(highs) < min_required or len(lows) < min_required:
            return None
        
        # Use only the lookback period
        recent_highs = highs[-self.lookback:]
        recent_lows = lows[-self.lookback:]
        recent_closes = closes[-self.lookback:]
        
        # Find swing points
        swing_highs = self._find_swing_highs(recent_highs, recent_closes)
        swing_lows = self._find_swing_lows(recent_lows, recent_closes)
        
        # Cluster into levels
        resistance_levels = self._cluster_levels(swing_highs, current_price)
        support_levels = self._cluster_levels(swing_lows, current_price)
        
        # Categorize relative to current price
        # Resistances are above current price, supports are below
        resistances = []
        supports = []
        
        for level in resistance_levels:
            level.level_type = 'resistance'
            if level.price > current_price:
                resistances.append(level)
            else:
                # Former resistance now below price = potential support
                level.level_type = 'support'
                supports.append(level)
        
        for level in support_levels:
            level.level_type = 'support'
            if level.price < current_price:
                supports.append(level)
            else:
                # Former support now above price = potential resistance
                level.level_type = 'resistance'
                resistances.append(level)
        
        # Sort by proximity to current price
        supports.sort(key=lambda x: current_price - x.price)
        resistances.sort(key=lambda x: x.price - current_price)
        
        # Find nearest levels
        nearest_support = supports[0].price if supports else None
        nearest_resistance = resistances[0].price if resistances else None
        
        # Calculate zones for nearest levels
        support_zone = None
        resistance_zone = None
        
        if supports:
            s = supports[0]
            half_width = s.price * (s.zone_width / 2) if s.zone_width > 0 else s.price * 0.001
            support_zone = (s.price - half_width, s.price + half_width)
        
        if resistances:
            r = resistances[0]
            half_width = r.price * (r.zone_width / 2) if r.zone_width > 0 else r.price * 0.001
            resistance_zone = (r.price - half_width, r.price + half_width)
        
        return {
            'supports': [{'price': s.price, 'strength': s.strength, 'zone_width': s.zone_width} 
                        for s in supports],
            'resistances': [{'price': r.price, 'strength': r.strength, 'zone_width': r.zone_width} 
                           for r in resistances],
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'support_zone': support_zone,
            'resistance_zone': resistance_zone
        }
    
    def is_near_support(self, current_price: float, highs: List[float], 
                        lows: List[float], closes: List[float],
                        tolerance_pct: float = 0.3) -> bool:
        """
        Check if current price is near a support level.
        
        Args:
            current_price: Current market price
            tolerance_pct: How close to support to be considered "near" (default 0.3%)
            
        Returns:
            True if near support, False otherwise
        """
        levels = self.find_levels(highs, lows, closes, current_price)
        if not levels or not levels['nearest_support']:
            return False
        
        support = levels['nearest_support']
        distance_pct = abs(current_price - support) / current_price * 100
        
        return distance_pct <= tolerance_pct
    
    def is_near_resistance(self, current_price: float, highs: List[float],
                           lows: List[float], closes: List[float],
                           tolerance_pct: float = 0.3) -> bool:
        """
        Check if current price is near a resistance level.
        
        Args:
            current_price: Current market price
            tolerance_pct: How close to resistance to be considered "near" (default 0.3%)
            
        Returns:
            True if near resistance, False otherwise
        """
        levels = self.find_levels(highs, lows, closes, current_price)
        if not levels or not levels['nearest_resistance']:
            return False
        
        resistance = levels['nearest_resistance']
        distance_pct = abs(resistance - current_price) / current_price * 100
        
        return distance_pct <= tolerance_pct
    
    def get_risk_reward_levels(self, current_price: float, highs: List[float],
                               lows: List[float], closes: List[float],
                               side: str = 'long') -> Optional[Dict]:
        """
        Get suggested stop-loss and take-profit based on S/R levels.
        
        Args:
            current_price: Entry price
            side: 'long' or 'short'
            
        Returns:
            Dictionary with suggested stop_loss and take_profit prices
        """
        levels = self.find_levels(highs, lows, closes, current_price)
        if not levels:
            return None
        
        if side == 'long':
            # Stop below support, target at resistance
            stop_loss = levels['nearest_support']
            take_profit = levels['nearest_resistance']
        else:
            # Stop above resistance, target at support
            stop_loss = levels['nearest_resistance']
            take_profit = levels['nearest_support']
        
        if not stop_loss or not take_profit:
            return None
        
        # Calculate risk/reward
        if side == 'long':
            risk = current_price - stop_loss
            reward = take_profit - current_price
        else:
            risk = stop_loss - current_price
            reward = current_price - take_profit
        
        risk_reward_ratio = reward / risk if risk > 0 else 0
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk': risk,
            'reward': reward,
            'risk_reward_ratio': risk_reward_ratio
        }
