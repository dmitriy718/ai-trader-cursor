"""E2E performance tests."""

import pytest
import asyncio
import time
from src.core.performance import PerformanceMonitor, measure_time, parallel_map


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_database_query_performance(temp_db, sample_klines):
    """Test database query performance with large dataset."""
    # Insert large dataset
    large_klines = sample_klines * 10  # 2000 klines
    await temp_db.insert_klines(large_klines)
    
    # Measure query time
    start = time.time()
    klines = await temp_db.get_klines('BTCUSDT', limit=200)
    elapsed = time.time() - start
    
    assert len(klines) == 200, "Should return requested limit"
    assert elapsed < 0.1, f"Query should be fast (<100ms), took {elapsed:.3f}s"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_database_operations(temp_db, sample_klines):
    """Test concurrent database operations performance."""
    # Insert initial data
    await temp_db.insert_klines(sample_klines)
    
    # Perform concurrent reads
    async def read_klines():
        return await temp_db.get_klines('BTCUSDT', limit=100)
    
    start = time.time()
    results = await asyncio.gather(*[read_klines() for _ in range(10)])
    elapsed = time.time() - start
    
    assert len(results) == 10, "All reads should complete"
    assert elapsed < 1.0, f"Concurrent reads should be fast (<1s), took {elapsed:.3f}s"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_scanner_parallel_scanning_performance(
    scanner_setup,
    mock_database,
    sample_klines,
    mock_binance_client
):
    """Test scanner parallel scanning performance."""
    mock_binance_client.get_klines = AsyncMock(return_value=sample_klines)
    
    start = time.time()
    signals = await scanner_setup.scan_all()
    elapsed = time.time() - start
    
    # Should complete quickly even with multiple symbols
    assert elapsed < 5.0, f"Parallel scanning should be fast (<5s), took {elapsed:.3f}s"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_cache_hit_performance():
    """Test cache hit performance improvement."""
    from src.core.cache import LRUCache
    
    cache = LRUCache(max_size=100, ttl_seconds=60)
    
    # First access - cache miss
    start = time.time()
    await cache.set('test_key', 'test_value')
    await cache.get('test_key')
    first_access = time.time() - start
    
    # Second access - cache hit
    start = time.time()
    value = await cache.get('test_key')
    second_access = time.time() - start
    
    assert value == 'test_value', "Cache should return correct value"
    assert second_access < first_access, "Cache hit should be faster"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_parallel_map_performance():
    """Test parallel_map utility performance."""
    async def slow_operation(n: int):
        await asyncio.sleep(0.01)  # Simulate slow operation
        return n * 2
    
    items = list(range(100))
    
    # Sequential
    start = time.time()
    sequential_results = []
    for item in items:
        result = await slow_operation(item)
        sequential_results.append(result)
    sequential_time = time.time() - start
    
    # Parallel
    start = time.time()
    parallel_results = await parallel_map(items, slow_operation, max_concurrent=10)
    parallel_time = time.time() - start
    
    assert len(parallel_results) == len(items), "All items should be processed"
    assert parallel_time < sequential_time, "Parallel should be faster than sequential"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.asyncio
async def test_batch_insert_performance(temp_db, sample_klines):
    """Test batch insert performance."""
    # Test with large dataset
    large_klines = sample_klines * 20  # 4000 klines
    
    start = time.time()
    await temp_db.insert_klines(large_klines)
    elapsed = time.time() - start
    
    # Should complete in reasonable time
    assert elapsed < 5.0, f"Batch insert should be fast (<5s), took {elapsed:.3f}s"
    
    # Verify all inserted
    klines = await temp_db.get_klines('BTCUSDT', limit=5000)
    assert len(klines) == len(large_klines), "All klines should be inserted"
