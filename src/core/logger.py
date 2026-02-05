"""Logging configuration for the trading bot."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger
from typing import Optional, Dict, Any
from contextvars import ContextVar
import contextvars

# Context variable for storing logging context
_log_context: ContextVar[Dict[str, Any]] = ContextVar('log_context', default={})


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: str = "INFO",
    max_bytes: int = 10485760,
    backup_count: int = 5,
    json_format: bool = False
) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    
    Args:
        name: Logger name
        log_file: Path to log file (optional)
        level: Logging level
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
        json_format: Whether to use JSON formatting
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    if json_format:
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if log_file is provided)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


class ContextualLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context information.
    
    Usage:
        logger = get_contextual_logger("MyComponent")
        with logger.context(symbol="BTCUSDT", trade_id=123):
            logger.info("Processing trade")
    """
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
        self._context_var = _log_context
    
    def process(self, msg, kwargs):
        """Add context to log messages."""
        # Get current context
        context = self._context_var.get({})
        
        # Merge with extra kwargs
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        
        # Add context to extra
        kwargs['extra'].update(context)
        kwargs['extra'].update(self.extra)
        
        return msg, kwargs
    
    def context(self, **kwargs):
        """
        Context manager for adding temporary context to logs.
        
        Example:
            with logger.context(symbol="BTCUSDT"):
                logger.info("Processing symbol")
        """
        return LogContext(self._context_var, kwargs)
    
    def set_context(self, **kwargs):
        """
        Set persistent context for this logger instance.
        
        Args:
            **kwargs: Context key-value pairs
        """
        current_context = self._context_var.get({}).copy()
        current_context.update(kwargs)
        self._context_var.set(current_context)
    
    def clear_context(self):
        """Clear all context."""
        self._context_var.set({})


class LogContext:
    """Context manager for logging context."""
    
    def __init__(self, context_var: ContextVar, new_context: Dict[str, Any]):
        self.context_var = context_var
        self.new_context = new_context
        self.old_context = {}
    
    def __enter__(self):
        # Save old context
        self.old_context = self.context_var.get({}).copy()
        # Merge with new context
        merged = self.old_context.copy()
        merged.update(self.new_context)
        self.context_var.set(merged)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore old context
        self.context_var.set(self.old_context)


def get_contextual_logger(
    name: str,
    log_file: Optional[str] = None,
    level: str = "INFO",
    max_bytes: int = 10485760,
    backup_count: int = 5,
    json_format: bool = False
) -> ContextualLoggerAdapter:
    """
    Get a contextual logger that supports context variables.
    
    Args:
        name: Logger name
        log_file: Path to log file (optional)
        level: Logging level
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
        json_format: Whether to use JSON formatting
    
    Returns:
        ContextualLoggerAdapter instance
    """
    base_logger = setup_logger(name, log_file, level, max_bytes, backup_count, json_format)
    return ContextualLoggerAdapter(base_logger)
