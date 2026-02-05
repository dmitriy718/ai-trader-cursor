"""E2E tests for complete trading flow."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.storage.models import OrderSide, OrderStatus, TradeStatus
from src.trading.engine import TradingEngine


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_trading_flow(
    trading_engine_setup: TradingEngine,
    sample_signal,
    mock_database,
    sample_klines
):
    """Test complete flow: signal -> order -> trade."""
    # Setup: Insert klines and signal
    await mock_database.insert_klines(sample_klines)
    signal_id = await mock_database.insert_signal(sample_signal)
    sample_signal.signal_id = signal_id
    
    # Step 1: Process signal
    await trading_engine_setup.process_signal(sample_signal)
    
    # Step 2: Verify order was created
    orders = await mock_database.get_open_orders()
    assert len(orders) > 0, "Order should be created"
    
    order = orders[0]
    assert order.symbol == 'BTCUSDT'
    assert order.side == OrderSide.BUY
    
    # Step 3: Simulate order fill
    order.status = OrderStatus.FILLED
    order.filled_quantity = 0.001
    order.filled_price = 50000.0
    await mock_database.update_order(order)
    
    # Step 4: Process fill
    await trading_engine_setup.fill_processor.process_order_fill(order)
    
    # Step 5: Verify trade was created
    trades = await mock_database.get_open_trades()
    assert len(trades) > 0, "Trade should be created"
    
    trade = trades[0]
    assert trade.symbol == 'BTCUSDT'
    assert trade.status == TradeStatus.OPEN
    assert trade.entry_price == 50000.0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signal_processing_with_low_confidence(
    trading_engine_setup: TradingEngine,
    sample_signal,
    mock_database
):
    """Test that low confidence signals are rejected."""
    # Set low confidence
    sample_signal.confidence = 0.3
    
    signal_id = await mock_database.insert_signal(sample_signal)
    sample_signal.signal_id = signal_id
    
    # Process signal
    await trading_engine_setup.process_signal(sample_signal)
    
    # Verify no order was created
    orders = await mock_database.get_open_orders()
    assert len(orders) == 0, "Low confidence signals should not create orders"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_management_rejection(
    trading_engine_setup: TradingEngine,
    sample_signal,
    mock_database,
    sample_klines
):
    """Test that risk management can reject trades."""
    # Setup: Insert klines
    await mock_database.insert_klines(sample_klines)
    
    # Mock risk manager to reject trade
    trading_engine_setup.risk_manager.check_trade_validity = MagicMock(
        return_value=(False, "Insufficient balance")
    )
    
    signal_id = await mock_database.insert_signal(sample_signal)
    sample_signal.signal_id = signal_id
    
    # Process signal
    await trading_engine_setup.process_signal(sample_signal)
    
    # Verify no order was created
    orders = await mock_database.get_open_orders()
    assert len(orders) == 0, "Risk management should reject invalid trades"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_trade_monitoring_and_exit(
    trading_engine_setup: TradingEngine,
    mock_database,
    sample_klines
):
    """Test trade monitoring and automatic exit."""
    # Create a trade
    from src.storage.models import Trade
    
    trade = Trade(
        trade_id=None,
        symbol='BTCUSDT',
        entry_order_id=1,
        exit_order_id=None,
        entry_price=50000.0,
        exit_price=None,
        quantity=0.001,
        side=OrderSide.BUY,
        status=TradeStatus.OPEN,
        pnl=0.0,
        strategy='trend',
        entry_time=datetime.now(),
        exit_time=None,
        stop_loss_price=49000.0,
        take_profit_price=51000.0,
        trailing_stop_price=None
    )
    
    trade_id = await mock_database.insert_trade(trade)
    trade.trade_id = trade_id
    
    # Update klines with price below stop loss
    stop_loss_klines = sample_klines.copy()
    stop_loss_klines[-1].close_price = 48000.0  # Below stop loss
    
    # Mock get_klines to return updated price
    trading_engine_setup.binance_client.get_klines = AsyncMock(
        return_value=stop_loss_klines[-50:]
    )
    
    # Run monitoring
    await trading_engine_setup.monitor_open_trades()
    
    # Verify trade was closed
    updated_trades = await mock_database.get_open_trades()
    assert len(updated_trades) == 0, "Trade should be closed when stop loss hit"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_concurrent_signal_processing(
    trading_engine_setup: TradingEngine,
    mock_database,
    sample_klines
):
    """Test processing multiple signals concurrently."""
    await mock_database.insert_klines(sample_klines)
    
    # Create multiple signals
    signals = []
    for i in range(5):
        signal = sample_signal.copy()
        signal.symbol = f'BTCUSDT' if i % 2 == 0 else 'ETHUSDT'
        signal.confidence = 0.7 + (i * 0.05)
        signal_id = await mock_database.insert_signal(signal)
        signal.signal_id = signal_id
        signals.append(signal)
    
    # Process signals concurrently
    tasks = [trading_engine_setup.process_signal(signal) for signal in signals]
    await asyncio.gather(*tasks)
    
    # Verify orders were created
    orders = await mock_database.get_open_orders()
    assert len(orders) >= 3, "Multiple orders should be created for valid signals"
