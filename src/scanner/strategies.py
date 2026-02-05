"""Scanner strategy implementations."""

from typing import Optional, Dict, Any, List
from datetime import datetime

from ..core.logger import setup_logger
from ..storage.models import Kline, ScannerSignal
from ..indicators.technical import TechnicalIndicators
from .base_strategy import BaseStrategy


class TrendStrategy(BaseStrategy):
    """Trend following strategy using EMA crossover and ADX."""
    
    def __init__(
        self,
        ema_fast: int = 5,
        ema_slow: int = 13,
        adx_threshold: float = 25.0
    ):
        """
        Initialize trend strategy.
        
        Args:
            ema_fast: Fast EMA period
            ema_slow: Slow EMA period
            adx_threshold: Minimum ADX for trend confirmation
        """
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.adx_threshold = adx_threshold
        self.logger = setup_logger("TrendStrategy")
    
    def scan(self, symbol: str, klines: List[Kline]) -> Optional[ScannerSignal]:
        """
        Scan for trend signals.
        
        Args:
            symbol: Trading pair symbol
            klines: Historical kline data
        
        Returns:
            ScannerSignal if signal detected, None otherwise
        """
        try:
            if len(klines) < max(self.ema_fast, self.ema_slow) + 14:
                return None
            
            df = TechnicalIndicators.klines_to_dataframe(klines)
            signal_data = TechnicalIndicators.detect_trend_signal(
                df,
                ema_fast_period=self.ema_fast,
                ema_slow_period=self.ema_slow,
                adx_threshold=self.adx_threshold
            )
            
            if signal_data:
                return self.create_signal(
                    symbol=symbol,
                    signal_type=signal_data['signal_type'],
                    confidence=signal_data['confidence'],
                    price=klines[-1].close_price,
                    indicators=signal_data['indicators']
                )
            
            return None
        except Exception as e:
            self.logger.error(
                f"[{self.__class__.__name__}] Failed to scan {symbol}: {e}",
                extra={'symbol': symbol, 'error_type': type(e).__name__}
            )
            return None


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands and RSI."""
    
    def __init__(
        self,
        bollinger_period: int = 20,
        bollinger_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: int = 30
    ):
        """
        Initialize mean reversion strategy.
        
        Args:
            bollinger_period: Bollinger Bands period
            bollinger_std: Bollinger Bands standard deviation
            rsi_period: RSI period
            rsi_oversold: RSI oversold threshold
        """
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.logger = setup_logger("MeanReversionStrategy")
    
    def scan(self, symbol: str, klines: List[Kline]) -> Optional[ScannerSignal]:
        """
        Scan for mean reversion signals.
        
        Args:
            symbol: Trading pair symbol
            klines: Historical kline data
        
        Returns:
            ScannerSignal if signal detected, None otherwise
        """
        try:
            if len(klines) < max(self.bollinger_period, self.rsi_period) + 1:
                return None
            
            df = TechnicalIndicators.klines_to_dataframe(klines)
            signal_data = TechnicalIndicators.detect_mean_reversion_signal(
                df,
                bollinger_period=self.bollinger_period,
                bollinger_std=self.bollinger_std,
                rsi_period=self.rsi_period,
                rsi_oversold=self.rsi_oversold
            )
            
            if signal_data:
                return self.create_signal(
                    symbol=symbol,
                    signal_type=signal_data['signal_type'],
                    confidence=signal_data['confidence'],
                    price=klines[-1].close_price,
                    indicators=signal_data['indicators']
                )
            
            return None
        except Exception as e:
            self.logger.error(
                f"[{self.__class__.__name__}] Failed to scan {symbol}: {e}",
                extra={'symbol': symbol, 'error_type': type(e).__name__}
            )
            return None


class MomentumStrategy(BaseStrategy):
    """Momentum strategy using RSI and volume."""
    
    def __init__(
        self,
        rsi_period: int = 14,
        rsi_threshold: int = 50,
        volume_multiplier: float = 1.5
    ):
        """
        Initialize momentum strategy.
        
        Args:
            rsi_period: RSI period
            rsi_threshold: RSI threshold for momentum
            volume_multiplier: Volume multiplier for confirmation
        """
        self.rsi_period = rsi_period
        self.rsi_threshold = rsi_threshold
        self.volume_multiplier = volume_multiplier
        self.logger = setup_logger("MomentumStrategy")
    
    def scan(self, symbol: str, klines: List[Kline]) -> Optional[ScannerSignal]:
        """
        Scan for momentum signals.
        
        Args:
            symbol: Trading pair symbol
            klines: Historical kline data
        
        Returns:
            ScannerSignal if signal detected, None otherwise
        """
        try:
            if len(klines) < self.rsi_period + 20:
                return None
            
            df = TechnicalIndicators.klines_to_dataframe(klines)
            signal_data = TechnicalIndicators.detect_momentum_signal(
                df,
                rsi_period=self.rsi_period,
                rsi_threshold=self.rsi_threshold,
                volume_multiplier=self.volume_multiplier
            )
            
            if signal_data:
                return self.create_signal(
                    symbol=symbol,
                    signal_type=signal_data['signal_type'],
                    confidence=signal_data['confidence'],
                    price=klines[-1].close_price,
                    indicators=signal_data['indicators']
                )
            
            return None
        except Exception as e:
            self.logger.error(
                f"[{self.__class__.__name__}] Failed to scan {symbol}: {e}",
                extra={'symbol': symbol, 'error_type': type(e).__name__}
            )
            return None
