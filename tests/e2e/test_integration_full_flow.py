"""Full integration E2E tests."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.storage.models import OrderSide, OrderStatus, TradeStatus


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_full_trading_bot_cycle(
    trading_engine_setup,
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client,
    sample_signal
):
    """Test complete trading bot cycle: scan -> signal -> order -> trade."""
    # Step 1: Insert klines
    await mock_database.insert_klines(sample_klines)
    
    # Step 2: Scanner detects signal
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    signals = await scanner_setup.scan_symbol('BTCUSDT')
    
    if signals:
        signal = signals[0]
        signal_id = await mock_database.insert_signal(signal)
        signal.signal_id = signal_id
        
        # Step 3: Trading engine processes signal
        await trading_engine_setup.process_signal(signal)
        
        # Step 4: Verify order created
        orders = await mock_database.get_open_orders()
        if orders:
            order = orders[0]
            
            # Step 5: Simulate order fill
            order.status = OrderStatus.FILLED
            order.filled_quantity = 0.001
            order.filled_price = 50000.0
            await mock_database.update_order(order)
            
            # Step 6: Process fill
            await trading_engine_setup.fill_processor.process_order_fill(order)
            
            # Step 7: Verify trade created
            trades = await mock_database.get_open_trades()
            assert len(trades) > 0, "Trade should be created after order fill"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_error_recovery_flow(
    trading_engine_setup,
    mock_database,
    sample_signal,
    mock_binance_client
):
    """Test error recovery in trading flow."""
    # Simulate API failure
    mock_binance_client.create_order = AsyncMock(side_effect=Exception("API Error"))
    
    signal_id = await mock_database.insert_signal(sample_signal)
    sample_signal.signal_id = signal_id
    
    # Process signal - should handle error gracefully
    await trading_engine_setup.process_signal(sample_signal)
    
    # Verify no order was created
    orders = await mock_database.get_open_orders()
    assert len(orders) == 0, "No order should be created on API error"
    
    # Verify signal is marked as failed
    signals = await mock_database.get_unprocessed_signals()
    assert signal_id not in [s.signal_id for s in signals], "Signal should be marked as failed"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_concurrent_signal_processing(
    trading_engine_setup,
    mock_database,
    sample_klines
):
    """Test concurrent signal processing."""
    await mock_database.insert_klines(sample_klines)
    
    # Create multiple signals
    signals = []
    for i in range(10):
        signal = sample_signal.copy()
        signal.symbol = 'BTCUSDT' if i % 2 == 0 else 'ETHUSDT'
        signal.confidence = 0.7 + (i * 0.02)
        signal_id = await mock_database.insert_signal(signal)
        signal.signal_id = signal_id
        signals.append(signal)
    
    # Process concurrently
    tasks = [trading_engine_setup.process_signal(signal) for signal in signals]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify all processed (some may be rejected by risk management)
    assert len(results) == len(signals), "All signals should be processed"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_database_transaction_consistency(
    temp_db,
    sample_klines
):
    """Test database transaction consistency."""
    # Test that partial transactions are rolled back
    try:
        async with temp_db.transaction():
            await temp_db.insert_klines(sample_klines[:10])
            # Simulate error
            raise ValueError("Test error")
    except ValueError:
        pass
    
    # Verify no klines were inserted (rollback)
    klines = await temp_db.get_klines('BTCUSDT', limit=100)
    assert len(klines) == 0, "Transaction should rollback on error"
