"""E2E tests for database operations."""

import pytest
from datetime import datetime
from src.storage.models import Order, Trade, OrderSide, OrderStatus, TradeStatus, SignalType


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_database_transaction_rollback(temp_db):
    """Test that database transactions rollback on error."""
    async with temp_db.transaction() as conn:
        # Insert an order
        order = Order(
            order_id=None,
            binance_order_id=12345,
            symbol='BTCUSDT',
            side=OrderSide.BUY,
            order_type='MARKET',
            quantity=0.001,
            price=50000.0,
            status=OrderStatus.PENDING,
            filled_quantity=0.0,
            filled_price=0.0,
            created_at=datetime.now()
        )
        
        order_id = await temp_db.insert_order(order)
        assert order_id is not None
        
        # Simulate error - transaction should rollback
        raise ValueError("Test error")
    
    # Verify order was not persisted (rollback)
    orders = await temp_db.get_open_orders()
    assert len(orders) == 0, "Transaction should rollback on error"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_database_batch_insert_klines(temp_db, sample_klines):
    """Test batch insertion of klines."""
    # Insert large batch
    await temp_db.insert_klines(sample_klines)
    
    # Verify all klines were inserted
    # Note: Would need a count method, but we can verify by querying
    klines = await temp_db.get_klines('BTCUSDT', limit=1000)
    assert len(klines) == len(sample_klines), "All klines should be inserted"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_database_signal_processing_atomicity(temp_db, sample_signal):
    """Test atomic signal processing."""
    # Insert signal
    signal_id = await temp_db.insert_signal(sample_signal)
    
    # Mark as processing
    success = await temp_db.mark_signal_processing(signal_id)
    assert success, "Should mark signal as processing"
    
    # Try to mark again (should fail)
    success2 = await temp_db.mark_signal_processing(signal_id)
    assert not success2, "Should not mark already processing signal"
    
    # Mark as processed
    await temp_db.mark_signal_processed(signal_id)
    
    # Verify signal is processed
    signals = await temp_db.get_unprocessed_signals()
    assert signal_id not in [s.signal_id for s in signals], "Signal should be marked as processed"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_database_query_pagination(temp_db, sample_klines):
    """Test database query pagination."""
    # Insert klines
    await temp_db.insert_klines(sample_klines)
    
    # Query with limit
    klines_page1 = await temp_db.get_klines('BTCUSDT', limit=50)
    assert len(klines_page1) <= 50, "Should respect limit"
    
    # Query with different limit
    klines_page2 = await temp_db.get_klines('BTCUSDT', limit=100)
    assert len(klines_page2) <= 100, "Should respect different limit"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_database_concurrent_access(temp_db, sample_klines):
    """Test database handles concurrent access."""
    # Insert klines concurrently
    tasks = [
        temp_db.insert_klines(sample_klines[i:i+50])
        for i in range(0, len(sample_klines), 50)
    ]
    await asyncio.gather(*tasks)
    
    # Verify all klines were inserted
    klines = await temp_db.get_klines('BTCUSDT', limit=1000)
    assert len(klines) == len(sample_klines), "Concurrent inserts should work correctly"
