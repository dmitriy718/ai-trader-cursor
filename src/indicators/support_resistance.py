"""Support and resistance level detection."""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional
from collections import defaultdict

from ..core.logger import setup_logger
from ..storage.models import Kline


class SupportResistanceDetector:
    """Detect support and resistance levels from price action."""
    
    def __init__(self, lookback_periods: int = 50, min_touches: int = 2):
        """
        Initialize support/resistance detector.
        
        Args:
            lookback_periods: Number of periods to look back
            min_touches: Minimum touches to consider a level valid
        """
        self.lookback_periods = lookback_periods
        self.min_touches = min_touches
        self.logger = setup_logger("SupportResistanceDetector")
    
    def detect_levels(self, klines: List[Kline]) -> Tuple[List[float], List[float]]:
        """
        Detect support and resistance levels.
        
        Args:
            klines: List of kline data
        
        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        if len(klines) < self.lookback_periods:
            return [], []
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame({
                'high': [k.high_price for k in klines],
                'low': [k.low_price for k in klines],
                'close': [k.close_price for k in klines]
            })
            
            # Use recent data
            recent_df = df.tail(self.lookback_periods)
            
            # Find local minima (support) and maxima (resistance)
            support_levels = self._find_support_levels(recent_df)
            resistance_levels = self._find_resistance_levels(recent_df)
            
            return support_levels, resistance_levels
        
        except Exception as e:
            self.logger.error(f"Error detecting support/resistance: {e}")
            return [], []
    
    def _find_support_levels(self, df: pd.DataFrame) -> List[float]:
        """Find support levels (local minima)."""
        support_levels = []
        
        # Find local minima
        lows = df['low'].values
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                # Check if this level has been touched multiple times
                level = float(lows[i])
                touches = sum(1 for low in lows if abs(low - level) / level < 0.01)
                if touches >= self.min_touches:
                    support_levels.append(level)
        
        # Remove duplicates and sort
        support_levels = sorted(set(support_levels))
        
        # Return strongest levels (most touches)
        return support_levels[-3:] if len(support_levels) > 3 else support_levels
    
    def _find_resistance_levels(self, df: pd.DataFrame) -> List[float]:
        """Find resistance levels (local maxima)."""
        resistance_levels = []
        
        # Find local maxima
        highs = df['high'].values
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                # Check if this level has been touched multiple times
                level = float(highs[i])
                touches = sum(1 for high in highs if abs(high - level) / level < 0.01)
                if touches >= self.min_touches:
                    resistance_levels.append(level)
        
        # Remove duplicates and sort
        resistance_levels = sorted(set(resistance_levels))
        
        # Return strongest levels (most touches)
        return resistance_levels[-3:] if len(resistance_levels) > 3 else resistance_levels
    
    def is_near_support(self, price: float, support_levels: List[float], threshold_percent: float = 1.0) -> bool:
        """Check if price is near a support level."""
        for level in support_levels:
            if abs(price - level) / level * 100 <= threshold_percent:
                return True
        return False
    
    def is_near_resistance(self, price: float, resistance_levels: List[float], threshold_percent: float = 1.0) -> bool:
        """Check if price is near a resistance level."""
        for level in resistance_levels:
            if abs(price - level) / level * 100 <= threshold_percent:
                return True
        return False
