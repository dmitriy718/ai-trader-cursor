"""Pytest configuration and shared fixtures."""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

from src.storage.database import Database
from src.api.binance_client import BinanceClient
from src.risk.manager import RiskManager
from src.ml.predictor import PricePredictor
from src.scanner.scanner import MarketScanner
from src.trading.engine import TradingEngine
from src.dashboard.api import DashboardAPI
from src.core.notifications import NotificationManager
from src.storage.models import Kline, ScannerSignal, OrderSide


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_db() -> AsyncGenerator[Database, None]:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        db = Database(db_path=db_path)
        await db.initialize()
        yield db
    finally:
        await db.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture
def mock_binance_client() -> MagicMock:
    """Create a mock Binance client."""
    mock_client = MagicMock()
    mock_client.get_account = AsyncMock(return_value={'balances': [{'asset': 'USDT', 'free': '10000.0'}]})
    mock_client.get_klines = AsyncMock(return_value=[])
    mock_client.get_order_book = AsyncMock(return_value={'bids': [[50000, 1]], 'asks': [[50001, 1]]})
    mock_client.create_order = AsyncMock(return_value=MagicMock(
        binance_order_id=12345,
        symbol='BTCUSDT',
        side=OrderSide.BUY,
        status='FILLED',
        filled_quantity=0.001,
        filled_price=50000.0
    ))
    mock_client.cancel_order = AsyncMock(return_value=True)
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
async def mock_database(temp_db: Database) -> Database:
    """Return a mock database instance."""
    return temp_db


@pytest.fixture
def mock_risk_manager() -> RiskManager:
    """Create a risk manager instance."""
    return RiskManager(
        risk_per_trade=0.02,
        max_position_size_usd=1000.0,
        daily_loss_limit_usd=100.0,
        trade_cooldown_seconds=300
    )


@pytest.fixture
def mock_price_predictor() -> MagicMock:
    """Create a mock price predictor."""
    mock_predictor = MagicMock(spec=PricePredictor)
    mock_predictor.predict = AsyncMock(return_value={
        'direction': 'UP',
        'confidence': 0.75,
        'prediction': [[0.25, 0.75]],
        'current_price': 50000.0
    })
    return mock_predictor


@pytest.fixture
def mock_notification_manager() -> MagicMock:
    """Create a mock notification manager."""
    mock_notifier = MagicMock(spec=NotificationManager)
    mock_notifier.send_trade_alert = AsyncMock()
    mock_notifier.send_signal_alert = AsyncMock()
    mock_notifier.send_error_alert = AsyncMock()
    return mock_notifier


@pytest.fixture
def sample_klines() -> list[Kline]:
    """Generate sample kline data for testing."""
    from datetime import datetime, timedelta
    
    klines = []
    base_time = datetime.now() - timedelta(minutes=200)
    base_price = 50000.0
    
    for i in range(200):
        time = base_time + timedelta(minutes=i)
        price_change = (i % 10 - 5) * 10  # Oscillating price
        price = base_price + price_change
        
        klines.append(Kline(
            symbol='BTCUSDT',
            open_time=time,
            close_time=time + timedelta(minutes=1),
            open_price=price - 5,
            high_price=price + 10,
            low_price=price - 10,
            close_price=price,
            volume=100.0 + i,
            quote_volume=(100.0 + i) * price,
            trades=50 + i,
            taker_buy_base_volume=50.0 + i,
            taker_buy_quote_volume=(50.0 + i) * price
        ))
    
    return klines


@pytest.fixture
def sample_signal() -> ScannerSignal:
    """Create a sample scanner signal."""
    from datetime import datetime
    
    return ScannerSignal(
        signal_id=None,
        symbol='BTCUSDT',
        strategy='trend',
        signal_type='BUY',
        confidence=0.75,
        price=50000.0,
        indicators={'ema_fast': 50100, 'ema_slow': 49900, 'adx': 30.0},
        created_at=datetime.now(),
        processed=False
    )


@pytest.fixture
async def trading_engine_setup(
    mock_database: Database,
    mock_binance_client: MagicMock,
    mock_risk_manager: RiskManager,
    mock_price_predictor: MagicMock,
    mock_notification_manager: MagicMock
) -> TradingEngine:
    """Create a trading engine instance for testing."""
    engine = TradingEngine(
        binance_client=mock_binance_client,
        database=mock_database,
        risk_manager=mock_risk_manager,
        price_predictor=mock_price_predictor,
        notification_manager=mock_notification_manager,
        trading_enabled=True
    )
    return engine


@pytest.fixture
async def scanner_setup(
    mock_database: Database,
    mock_binance_client: MagicMock
) -> MarketScanner:
    """Create a scanner instance for testing."""
    scanner = MarketScanner(
        binance_client=mock_binance_client,
        database=mock_database,
        symbols=['BTCUSDT', 'ETHUSDT'],
        interval_seconds=60
    )
    return scanner


@pytest.fixture
async def dashboard_setup(
    mock_database: Database,
    trading_engine_setup: TradingEngine,
    scanner_setup: MarketScanner
) -> DashboardAPI:
    """Create a dashboard API instance for testing."""
    dashboard = DashboardAPI(
        database=mock_database,
        trading_engine=trading_engine_setup,
        scanner=scanner_setup,
        host='127.0.0.1',
        port=8001  # Different port to avoid conflicts
    )
    return dashboard
