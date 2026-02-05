"""Technical indicators using TA-Lib and Pandas."""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

from ..storage.models import Kline


class TechnicalIndicators:
    """Technical indicators calculator."""
    
    @staticmethod
    def klines_to_dataframe(klines: list[Kline]) -> pd.DataFrame:
        """Convert klines to pandas DataFrame."""
        data = {
            'open': [k.open_price for k in klines],
            'high': [k.high_price for k in klines],
            'low': [k.low_price for k in klines],
            'close': [k.close_price for k in klines],
            'volume': [k.volume for k in klines]
        }
        return pd.DataFrame(data)
    
    @staticmethod
    def calculate_ema(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
        """Calculate Exponential Moving Average."""
        ema_indicator = EMAIndicator(close=df[column], window=period)
        return ema_indicator.ema_indicator()
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        rsi_indicator = RSIIndicator(close=df['close'], window=period)
        return rsi_indicator.rsi()
    
    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> Dict[str, pd.Series]:
        """Calculate Average Directional Index."""
        adx_indicator = ADXIndicator(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=period
        )
        return {
            'adx': adx_indicator.adx(),
            'adx_pos': adx_indicator.adx_pos(),
            'adx_neg': adx_indicator.adx_neg()
        }
    
    @staticmethod
    def calculate_bollinger_bands(
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands."""
        bb_indicator = BollingerBands(
            close=df['close'],
            window=period,
            window_dev=std_dev
        )
        return {
            'bb_high': bb_indicator.bollinger_hband(),
            'bb_mid': bb_indicator.bollinger_mavg(),
            'bb_low': bb_indicator.bollinger_lband()
        }
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        return true_range.rolling(window=period).mean()
    
    @staticmethod
    def calculate_volume_ma(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Volume Moving Average."""
        return df['volume'].rolling(window=period).mean()
    
    @staticmethod
    def get_latest_values(df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> Dict[str, float]:
        """Get latest values from indicator series."""
        latest = {}
        for name, series in indicators.items():
            if isinstance(series, pd.Series) and len(series) > 0:
                value = series.iloc[-1]
                latest[name] = float(value) if not pd.isna(value) else None
            elif isinstance(series, dict):
                latest[name] = TechnicalIndicators.get_latest_values(df, series)
            else:
                latest[name] = None
        return latest
    
    @staticmethod
    def detect_trend_signal(
        df: pd.DataFrame,
        ema_fast_period: int = 5,
        ema_slow_period: int = 13,
        adx_threshold: float = 25.0
    ) -> Optional[Dict[str, any]]:
        """
        Detect trend signal using EMA crossover and ADX.
        
        Returns:
            Dict with signal_type ('BUY' or 'SELL'), confidence, and indicators
        """
        if len(df) < max(ema_fast_period, ema_slow_period) + 14:
            return None
        
        # Calculate EMAs
        ema_fast = TechnicalIndicators.calculate_ema(df, ema_fast_period)
        ema_slow = TechnicalIndicators.calculate_ema(df, ema_slow_period)
        adx_data = TechnicalIndicators.calculate_adx(df)
        
        if len(ema_fast) < 2 or len(ema_slow) < 2:
            return None
        
        current_fast = ema_fast.iloc[-1]
        current_slow = ema_slow.iloc[-1]
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]
        current_adx = adx_data['adx'].iloc[-1]
        
        if pd.isna(current_fast) or pd.isna(current_slow) or pd.isna(current_adx):
            return None
        
        # Bullish crossover: fast EMA crosses above slow EMA
        bullish_cross = prev_fast <= prev_slow and current_fast > current_slow
        # Bearish crossover: fast EMA crosses below slow EMA
        bearish_cross = prev_fast >= prev_slow and current_fast < current_slow
        
        # ADX must be above threshold for strong trend
        if current_adx < adx_threshold:
            return None
        
        if bullish_cross:
            confidence = min(0.9, 0.5 + (current_adx / 100))
            return {
                'signal_type': 'BUY',
                'confidence': confidence,
                'indicators': {
                    'ema_fast': float(current_fast),
                    'ema_slow': float(current_slow),
                    'adx': float(current_adx)
                }
            }
        elif bearish_cross:
            confidence = min(0.9, 0.5 + (current_adx / 100))
            return {
                'signal_type': 'SELL',
                'confidence': confidence,
                'indicators': {
                    'ema_fast': float(current_fast),
                    'ema_slow': float(current_slow),
                    'adx': float(current_adx)
                }
            }
        
        return None
    
    @staticmethod
    def detect_mean_reversion_signal(
        df: pd.DataFrame,
        bollinger_period: int = 20,
        bollinger_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: int = 30
    ) -> Optional[Dict[str, any]]:
        """
        Detect mean reversion signal using Bollinger Bands and RSI.
        
        Returns:
            Dict with signal_type ('BUY' or None), confidence, and indicators
        """
        if len(df) < max(bollinger_period, rsi_period) + 1:
            return None
        
        bb = TechnicalIndicators.calculate_bollinger_bands(df, bollinger_period, bollinger_std)
        rsi = TechnicalIndicators.calculate_rsi(df, rsi_period)
        
        if len(bb['bb_low']) == 0 or len(rsi) == 0:
            return None
        
        current_price = df['close'].iloc[-1]
        current_bb_low = bb['bb_low'].iloc[-1]
        current_rsi = rsi.iloc[-1]
        
        if pd.isna(current_bb_low) or pd.isna(current_rsi):
            return None
        
        # Buy signal: price touches lower Bollinger Band and RSI is oversold
        if current_price <= current_bb_low and current_rsi <= rsi_oversold:
            confidence = 0.7 + (rsi_oversold - current_rsi) / 100
            confidence = min(0.9, confidence)
            return {
                'signal_type': 'BUY',
                'confidence': confidence,
                'indicators': {
                    'price': float(current_price),
                    'bb_low': float(current_bb_low),
                    'rsi': float(current_rsi)
                }
            }
        
        return None
    
    @staticmethod
    def detect_momentum_signal(
        df: pd.DataFrame,
        rsi_period: int = 14,
        rsi_threshold: int = 50,
        volume_multiplier: float = 1.5
    ) -> Optional[Dict[str, any]]:
        """
        Detect momentum signal using RSI and volume.
        
        Returns:
            Dict with signal_type ('BUY' or None), confidence, and indicators
        """
        if len(df) < rsi_period + 20:
            return None
        
        rsi = TechnicalIndicators.calculate_rsi(df, rsi_period)
        volume_ma = TechnicalIndicators.calculate_volume_ma(df, period=20)
        
        if len(rsi) < 2 or len(volume_ma) == 0:
            return None
        
        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        current_volume = df['volume'].iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        
        if pd.isna(current_rsi) or pd.isna(prev_rsi) or pd.isna(avg_volume):
            return None
        
        # Buy signal: RSI crosses above threshold with volume burst
        if prev_rsi <= rsi_threshold and current_rsi > rsi_threshold:
            if current_volume >= avg_volume * volume_multiplier:
                confidence = 0.6 + min(0.3, (current_rsi - rsi_threshold) / 100)
                return {
                    'signal_type': 'BUY',
                    'confidence': confidence,
                    'indicators': {
                        'rsi': float(current_rsi),
                        'prev_rsi': float(prev_rsi),
                        'volume': float(current_volume),
                        'avg_volume': float(avg_volume)
                    }
                }
        
        return None
