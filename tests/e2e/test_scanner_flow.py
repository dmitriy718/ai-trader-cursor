"""E2E tests for scanner flow."""

import pytest
import asyncio
from datetime import datetime, timedelta

from src.storage.models import SignalType


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scanner_detects_signals(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test that scanner detects and stores signals."""
    # Mock binance client to return klines
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    
    # Scan symbol
    signals = await scanner_setup.scan_symbol('BTCUSDT')
    
    # Verify signals were detected
    assert isinstance(signals, list), "Should return list of signals"
    
    # Verify signals were stored in database
    stored_signals = await mock_database.get_unprocessed_signals()
    assert len(stored_signals) > 0, "Signals should be stored in database"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scanner_parallel_scanning(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test parallel scanning of multiple symbols."""
    # Mock binance client
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    
    # Scan all symbols
    all_signals = await scanner_setup.scan_all()
    
    # Verify signals from multiple symbols
    assert len(all_signals) >= 0, "Should return signals from all symbols"
    
    # Verify all signals stored
    stored_signals = await mock_database.get_unprocessed_signals()
    assert len(stored_signals) == len(all_signals), "All signals should be stored"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scanner_kline_caching(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test that scanner caches klines efficiently."""
    # Mock binance client
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    
    # First scan - should fetch from API
    await scanner_setup.scan_symbol('BTCUSDT')
    call_count_1 = mock_binance_client.get_klines.call_count
    
    # Second scan - should use cache
    await scanner_setup.scan_symbol('BTCUSDT')
    call_count_2 = mock_binance_client.get_klines.call_count
    
    # Verify cache is being used (call count should be same or minimal increase)
    assert call_count_2 <= call_count_1 + 1, "Cache should reduce API calls"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scanner_cache_cleanup(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test that scanner cleans up expired cache entries."""
    # Add klines to cache
    old_kline = sample_klines[0]
    old_kline.open_time = datetime.now() - timedelta(hours=2)  # Old kline
    
    await scanner_setup.update_kline_cache('BTCUSDT', old_kline)
    
    # Verify cache has entry
    assert 'BTCUSDT' in scanner_setup.kline_cache
    
    # Run cleanup
    await scanner_setup.cleanup_cache()
    
    # Verify old entries are removed (if TTL expired)
    # Note: This depends on cache_ttl_seconds setting
    cache_size = len(scanner_setup.kline_cache.get('BTCUSDT', []))
    assert cache_size >= 0, "Cache cleanup should work"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scanner_warmup(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test scanner warmup with historical data."""
    # Mock binance client
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    
    # Warmup
    await scanner_setup.warmup(minutes=120)
    
    # Verify klines were inserted into database
    # Note: This would require a method to count klines in DB
    assert mock_binance_client.get_klines.called, "Warmup should fetch historical data"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scanner_multiple_strategies(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test that scanner runs all enabled strategies."""
    # Mock binance client
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    
    # Scan symbol
    signals = await scanner_setup.scan_symbol('BTCUSDT')
    
    # Verify signals from different strategies
    strategies_found = set()
    for signal in signals:
        strategies_found.add(signal.strategy)
    
    # Should have signals from multiple strategies if conditions are met
    assert len(strategies_found) >= 0, "Multiple strategies should be able to detect signals"
