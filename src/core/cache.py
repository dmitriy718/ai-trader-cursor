"""In-memory caching utilities for performance optimization."""

import asyncio
from typing import Dict, Any, Optional, Callable, TypeVar
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import json

T = TypeVar('T')


class LRUCache:
    """
    Thread-safe LRU cache with TTL support.
    
    Optimized for high-frequency reads with periodic cleanup.
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: Optional[int] = None):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of items in cache
            ttl_seconds: Time-to-live in seconds (None for no expiration)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._lock = asyncio.Lock()
        self._access_order: list[str] = []
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        async with self._lock:
            if key not in self._cache:
                return None
            
            value, timestamp = self._cache[key]
            
            # Check TTL
            if self.ttl_seconds and (datetime.now() - timestamp).total_seconds() > self.ttl_seconds:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return None
            
            # Update access order (move to end)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            return value
    
    async def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        async with self._lock:
            # Remove oldest if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                if self._access_order:
                    oldest_key = self._access_order.pop(0)
                    del self._cache[oldest_key]
            
            self._cache[key] = (value, datetime.now())
            if key not in self._access_order:
                self._access_order.append(key)
    
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()
    
    async def cleanup_expired(self) -> int:
        """
        Remove expired entries.
        
        Returns:
            Number of entries removed
        """
        if not self.ttl_seconds:
            return 0
        
        async with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if (now - timestamp).total_seconds() > self.ttl_seconds
            ]
            
            for key in expired_keys:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
            
            return len(expired_keys)
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


def cached_async(
    ttl_seconds: Optional[int] = None,
    max_size: int = 1000,
    key_func: Optional[Callable] = None
):
    """
    Decorator for caching async function results.
    
    Args:
        ttl_seconds: Cache TTL in seconds
        max_size: Maximum cache size
        key_func: Custom key function (default: uses function name + args hash)
    
    Example:
        @cached_async(ttl_seconds=60)
        async def expensive_operation(symbol: str):
            return await fetch_data(symbol)
    """
    cache = LRUCache(max_size=max_size, ttl_seconds=ttl_seconds)
    
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: hash function name + args
                key_data = {
                    'func': func.__name__,
                    'args': args,
                    'kwargs': kwargs
                }
                key_str = json.dumps(key_data, sort_keys=True, default=str)
                cache_key = hashlib.md5(key_str.encode()).hexdigest()
            
            # Try cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call function
            result = await func(*args, **kwargs)
            
            # Store in cache
            await cache.set(cache_key, result)
            
            return result
        
        # Attach cache to function for manual control
        wrapper.cache = cache
        return wrapper
    
    return decorator
