"""Configuration management for the trading bot."""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml


class TradingConfig(BaseSettings):
    """Trading configuration."""
    enabled: bool = Field(default=False, description="Enable live trading")
    risk_per_trade: float = Field(default=0.02, ge=0.0, le=1.0)
    max_position_size_usd: float = Field(default=1000.0, gt=0.0)
    daily_loss_limit_usd: float = Field(default=100.0, gt=0.0)
    trade_cooldown_seconds: int = Field(default=300, gt=0)


class ScannerConfig(BaseSettings):
    """Scanner configuration."""
    interval_seconds: int = Field(default=60, gt=0)
    symbols: List[str] = Field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT",
        "DOGEUSDT", "XRPUSDT", "LTCUSDT", "LINKUSDT", "SHIBUSDT"
    ])
    
    class TrendStrategy(BaseSettings):
        enabled: bool = True
        ema_fast: int = 5
        ema_slow: int = 13
        adx_threshold: float = 25.0
    
    class MeanReversionStrategy(BaseSettings):
        enabled: bool = True
        bollinger_period: int = 20
        bollinger_std: float = 2.0
        rsi_period: int = 14
        rsi_oversold: int = 30
    
    class MomentumStrategy(BaseSettings):
        enabled: bool = True
        rsi_period: int = 14
        rsi_threshold: int = 50
        volume_multiplier: float = 1.5
    
    trend: TrendStrategy = Field(default_factory=TrendStrategy)
    mean_reversion: MeanReversionStrategy = Field(default_factory=MeanReversionStrategy)
    momentum: MomentumStrategy = Field(default_factory=MomentumStrategy)


class RiskManagementConfig(BaseSettings):
    """Risk management configuration."""
    adx_chop_threshold: float = Field(default=25.0, gt=0.0)
    atr_multiplier: float = Field(default=2.0, gt=0.0)
    trailing_stop_enabled: bool = True
    breakeven_enabled: bool = True
    breakeven_trigger_percent: float = Field(default=0.5, gt=0.0)
    
    class LiquidityConfig(BaseSettings):
        max_spread_percent: float = Field(default=0.5, gt=0.0)
        min_book_liquidity_usd: float = Field(default=5000.0, gt=0.0)
        order_book_imbalance_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    
    liquidity: LiquidityConfig = Field(default_factory=LiquidityConfig)


class PerformanceConfig(BaseSettings):
    """Performance optimization configuration."""
    kline_buffer_size: int = Field(default=200, gt=0)
    ram_cache_enabled: bool = True
    historical_warmup_minutes: int = Field(default=120, gt=0)


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    path: str = Field(default="/app/data/trading_bot.db")
    wal_mode: bool = True
    connection_pool_size: int = Field(default=10, gt=0)


class APIConfig(BaseSettings):
    """API server configuration."""
    host: str = "0.0.0.0"
    port: int = Field(default=8000, gt=0, lt=65536)
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    level: str = Field(default="INFO")
    file: str = Field(default="/app/logs/trading_bot.log")
    max_bytes: int = Field(default=10485760)  # 10MB
    backup_count: int = Field(default=5, gt=0)


class MLConfig(BaseSettings):
    """Machine learning configuration."""
    model_path: str = Field(default="/app/models/price_predictor.tflite")
    prediction_window_minutes: int = Field(default=5, gt=0)
    retrain_interval_hours: int = Field(default=24, gt=0)


class MonitoringConfig(BaseSettings):
    """Monitoring configuration."""
    health_check_interval_seconds: int = Field(default=30, gt=0)
    metrics_enabled: bool = True


class Config(BaseSettings):
    """Main configuration class."""
    trading: TradingConfig = Field(default_factory=TradingConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    risk_management: RiskManagementConfig = Field(default_factory=RiskManagementConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ml: MLConfig = Field(default_factory=MLConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    # Binance API credentials
    binance_api_key: str = Field(default="", description="Binance API key")
    binance_api_secret: str = Field(default="", description="Binance API secret")
    binance_testnet: bool = Field(default=False, description="Use Binance testnet")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_nested_delimiter = "__"


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file and environment variables.
    
    Validates and sanitizes all configuration values to prevent security issues.
    """
    import logging
    logger = logging.getLogger("ConfigLoader")
    
    config = Config()
    
    # Define allowed configuration keys to prevent arbitrary attribute setting
    ALLOWED_CONFIG_KEYS = {
        'trading', 'scanner', 'risk_management', 'performance',
        'database', 'api', 'logging', 'ml', 'monitoring'
    }
    
    # Load from YAML if provided
    if config_path:
        config_path_obj = Path(config_path)
        if not config_path_obj.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
        else:
            try:
                with open(config_path_obj, 'r') as f:
                    yaml_config: Dict[str, Any] = yaml.safe_load(f)
                    if yaml_config and isinstance(yaml_config, dict):
                        # Validate and merge YAML config
                        for key, value in yaml_config.items():
                            # Only allow known configuration keys
                            if key not in ALLOWED_CONFIG_KEYS:
                                logger.warning(
                                    f"Ignoring unknown config key: {key}. "
                                    f"Allowed keys: {', '.join(ALLOWED_CONFIG_KEYS)}"
                                )
                                continue
                            
                            # Validate key exists in config object
                            if not hasattr(config, key):
                                logger.warning(f"Config key '{key}' not found in Config class")
                                continue
                            
                            # Validate value type matches expected type
                            current_value = getattr(config, key)
                            if current_value is not None:
                                expected_type = type(current_value)
                                if not isinstance(value, expected_type) and not isinstance(value, dict):
                                    logger.warning(
                                        f"Config key '{key}' has wrong type. "
                                        f"Expected {expected_type.__name__}, got {type(value).__name__}"
                                    )
                                    continue
                            
                            # Set the value
                            try:
                                setattr(config, key, value)
                            except (ValueError, TypeError) as e:
                                logger.error(f"Failed to set config key '{key}': {e}")
                                continue
            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML config file: {e}")
                raise ValueError(f"Invalid YAML configuration file: {e}") from e
            except Exception as e:
                logger.error(f"Error loading config file: {e}")
                raise ValueError(f"Failed to load configuration: {e}") from e
    
    # Override with environment variables (with validation)
    # Environment variables take precedence
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    testnet_str = os.getenv("BINANCE_TESTNET", "false").strip().lower()
    
    # Validate API key format (basic check)
    if api_key:
        if len(api_key) < 10:
            logger.warning("BINANCE_API_KEY appears to be too short")
        config.binance_api_key = api_key
    
    # Validate API secret format (basic check)
    if api_secret:
        if len(api_secret) < 10:
            logger.warning("BINANCE_API_SECRET appears to be too short")
        config.binance_api_secret = api_secret
    
    # Validate testnet flag
    if testnet_str in ('true', '1', 'yes', 'on'):
        config.binance_testnet = True
    elif testnet_str in ('false', '0', 'no', 'off', ''):
        config.binance_testnet = False
    else:
        logger.warning(f"Invalid BINANCE_TESTNET value: {testnet_str}, defaulting to False")
        config.binance_testnet = False
    
    return config
