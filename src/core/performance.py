"""Performance optimization utilities."""

import asyncio
import time
from typing import Callable, Any, TypeVar, Coroutine, Dict
from functools import wraps
from contextlib import asynccontextmanager
import functools

T = TypeVar('T')


def async_timed(func: Callable) -> Callable:
    """Decorator to measure async function execution time."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            elapsed = time.time() - start
            if elapsed > 1.0:  # Log slow operations (>1 second)
                print(f"[PERF] {func.__name__} took {elapsed:.2f}s")
    return wrapper


class PerformanceMonitor:
    """Monitor and track performance metrics."""
    
    def __init__(self):
        self.metrics: Dict[str, list[float]] = {}
        self._lock = asyncio.Lock()
    
    async def record(self, operation: str, duration: float):
        """Record operation duration."""
        async with self._lock:
            if operation not in self.metrics:
                self.metrics[operation] = []
            self.metrics[operation].append(duration)
            
            # Keep only last 1000 measurements
            if len(self.metrics[operation]) > 1000:
                self.metrics[operation] = self.metrics[operation][-1000:]
    
    async def get_stats(self, operation: str) -> Dict[str, float]:
        """Get statistics for an operation."""
        async with self._lock:
            if operation not in self.metrics or not self.metrics[operation]:
                return {}
            
            durations = self.metrics[operation]
            return {
                'count': len(durations),
                'min': min(durations),
                'max': max(durations),
                'avg': sum(durations) / len(durations),
                'p50': sorted(durations)[len(durations) // 2],
                'p95': sorted(durations)[int(len(durations) * 0.95)],
                'p99': sorted(durations)[int(len(durations) * 0.99)]
            }
    
    async def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all operations."""
        async with self._lock:
            return {
                op: await self.get_stats(op)
                for op in self.metrics.keys()
            }


# Global performance monitor instance
_perf_monitor = PerformanceMonitor()


@asynccontextmanager
async def measure_time(operation: str):
    """Context manager to measure operation time."""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        await _perf_monitor.record(operation, duration)


def batch_process(items: list[T], batch_size: int = 100) -> list[list[T]]:
    """
    Split items into batches for processing.
    
    Args:
        items: List of items to batch
        batch_size: Size of each batch
    
    Returns:
        List of batches
    """
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


async def parallel_map(
    items: list[T],
    func: Callable[[T], Coroutine[Any, Any, Any]],
    max_concurrent: int = 10
) -> list[Any]:
    """
    Process items in parallel with concurrency limit.
    
    Args:
        items: List of items to process
        func: Async function to apply to each item
        max_concurrent: Maximum concurrent operations
    
    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_item(item: T):
        async with semaphore:
            return await func(item)
    
    tasks = [process_item(item) for item in items]
    return await asyncio.gather(*tasks, return_exceptions=True)
