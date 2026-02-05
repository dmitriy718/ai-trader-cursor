"""Base strategy class with common functionality."""

from typing import Optional, Dict, Any, List
from datetime import datetime

from ..storage.models import Kline, ScannerSignal


class BaseStrategy:
    """Base class for scanner strategies with common functionality."""
    
    def create_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        price: float,
        indicators: Dict[str, Any]
    ) -> ScannerSignal:
        """
        Create a scanner signal with standardized format.
        
        Args:
            symbol: Trading pair symbol
            signal_type: Signal type (BUY, SELL, etc.)
            confidence: Signal confidence (0.0 to 1.0)
            price: Current price
            indicators: Indicator values
        
        Returns:
            ScannerSignal object
        
        Example:
            >>> signal = strategy.create_signal(
            ...     symbol="BTCUSDT",
            ...     signal_type="BUY",
            ...     confidence=0.75,
            ...     price=50000.0,
            ...     indicators={"ema_fast": 50100, "ema_slow": 49900}
            ... )
        """
        strategy_name = self.__class__.__name__.lower().replace('strategy', '')
        
        return ScannerSignal(
            signal_id=None,
            symbol=symbol,
            strategy=strategy_name,
            signal_type=signal_type,
            confidence=confidence,
            price=price,
            indicators=indicators,
            created_at=datetime.now(),
            processed=False
        )
    
    def validate_klines(self, klines: List[Kline], min_required: int) -> bool:
        """
        Validate that we have enough klines for analysis.
        
        Args:
            klines: List of klines
            min_required: Minimum number of klines required
        
        Returns:
            True if enough klines, False otherwise
        """
        return len(klines) >= min_required
