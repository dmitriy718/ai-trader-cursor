"""Breakout trading strategy."""

from typing import Optional, Dict, Any, List
from datetime import datetime

from ..core.logger import setup_logger
from ..storage.models import Kline, ScannerSignal
from ..indicators.support_resistance import SupportResistanceDetector


class BreakoutStrategy:
    """Breakout trading strategy detecting price breakouts from consolidation."""
    
    def __init__(
        self,
        consolidation_periods: int = 20,
        breakout_threshold_percent: float = 1.0,
        volume_multiplier: float = 1.5
    ):
        """
        Initialize breakout strategy.
        
        Args:
            consolidation_periods: Periods to look for consolidation
            breakout_threshold_percent: Percentage above/below to consider breakout
            volume_multiplier: Volume multiplier for confirmation
        """
        self.consolidation_periods = consolidation_periods
        self.breakout_threshold_percent = breakout_threshold_percent
        self.volume_multiplier = volume_multiplier
        self.logger = setup_logger("BreakoutStrategy")
        self.sr_detector = SupportResistanceDetector()
    
    def scan(self, symbol: str, klines: List[Kline]) -> Optional[ScannerSignal]:
        """
        Scan for breakout signals.
        
        Args:
            symbol: Trading pair symbol
            klines: Historical kline data
        
        Returns:
            ScannerSignal if breakout detected, None otherwise
        """
        try:
            if len(klines) < self.consolidation_periods + 5:
                return None
            
            # Get recent klines
            recent_klines = klines[-self.consolidation_periods-5:]
            
            # Detect support/resistance levels
            support_levels, resistance_levels = self.sr_detector.detect_levels(recent_klines)
            
            if not support_levels and not resistance_levels:
                return None
            
            current_price = recent_klines[-1].close_price
            current_volume = recent_klines[-1].volume
            
            # Calculate average volume
            avg_volume = sum(k.volume for k in recent_klines[:-1]) / len(recent_klines[:-1])
            
            # Check for upward breakout (above resistance)
            if resistance_levels:
                highest_resistance = max(resistance_levels)
                if current_price > highest_resistance * (1 + self.breakout_threshold_percent / 100):
                    if current_volume >= avg_volume * self.volume_multiplier:
                        confidence = min(0.9, 0.6 + (current_volume / avg_volume - 1) * 0.1)
                        return self.create_signal(
                            symbol=symbol,
                            signal_type="BUY",
                            confidence=confidence,
                            price=current_price,
                            indicators={
                                'resistance_level': highest_resistance,
                                'breakout_percent': ((current_price - highest_resistance) / highest_resistance) * 100,
                                'volume_ratio': current_volume / avg_volume
                            }
                        )
            
            # Check for downward breakout (below support)
            if support_levels:
                lowest_support = min(support_levels)
                if current_price < lowest_support * (1 - self.breakout_threshold_percent / 100):
                    if current_volume >= avg_volume * self.volume_multiplier:
                        confidence = min(0.9, 0.6 + (current_volume / avg_volume - 1) * 0.1)
                        return self.create_signal(
                            symbol=symbol,
                            signal_type="SELL",
                            confidence=confidence,
                            price=current_price,
                            indicators={
                                'support_level': lowest_support,
                                'breakout_percent': ((lowest_support - current_price) / lowest_support) * 100,
                                'volume_ratio': current_volume / avg_volume
                            }
                        )
            
            return None
        
        except Exception as e:
            self.logger.error(
                f"[{self.__class__.__name__}] Failed to scan {symbol}: {e}",
                extra={'symbol': symbol, 'error_type': type(e).__name__}
            )
            return None
