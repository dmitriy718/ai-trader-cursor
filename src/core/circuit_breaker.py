"""Circuit breaker pattern implementation for resilient API calls."""

import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any, TypeVar
from datetime import datetime, timedelta

from .logger import setup_logger

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for API calls.
    
    Prevents cascading failures by stopping requests when a service is failing.
    Automatically attempts recovery after a timeout period.
    
    Example:
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=Exception
        )
        
        result = await breaker.call(api_function, arg1, arg2)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception,
        name: str = "CircuitBreaker"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type that counts as failure
            name: Name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name
        self.logger = setup_logger(f"CircuitBreaker.{name}")
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.success_count = 0  # For half-open state
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
        
        Returns:
            Result of function call
        
        Raises:
            CircuitOpenError: If circuit is open
            Exception: Any exception raised by the function
        """
        async with self._lock:
            # Check if circuit should transition
            await self._check_state()
            
            # Reject if circuit is open
            if self.state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker {self.name} is OPEN. "
                    f"Last failure: {self.last_failure_time}"
                )
        
        # Execute the function
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Success - update state
            async with self._lock:
                await self._on_success()
            
            return result
        
        except self.expected_exception as e:
            # Failure - update state
            async with self._lock:
                await self._on_failure()
            
            raise
    
    async def _check_state(self):
        """Check and update circuit breaker state."""
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.logger.info(
                        f"Circuit breaker {self.name} transitioning to HALF_OPEN"
                    )
    
    async def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            # If we get a few successes, close the circuit
            if self.success_count >= 2:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.logger.info(
                    f"Circuit breaker {self.name} transitioning to CLOSED"
                )
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    async def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            # Failed again in half-open, go back to open
            self.state = CircuitState.OPEN
            self.success_count = 0
            self.logger.warning(
                f"Circuit breaker {self.name} transitioning back to OPEN"
            )
        elif self.state == CircuitState.CLOSED:
            # Check if we've exceeded threshold
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.logger.error(
                    f"Circuit breaker {self.name} opening after {self.failure_count} failures"
                )
    
    def reset(self):
        """Manually reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.logger.info(f"Circuit breaker {self.name} manually reset")
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.state


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass
