# Architecture Documentation

## System Overview

The AI Trading Bot is a production-ready cryptocurrency trading system built with Python 3.11, FastAPI, and Docker. It features multi-strategy market scanning, ML-based price prediction, advanced risk management, and comprehensive monitoring.

## Component Architecture

### 1. Core Components

#### Configuration System (`src/core/config.py`)
- Pydantic-based configuration management
- YAML file support with environment variable overrides
- Type-safe configuration classes
- **ENHANCEMENT**: Nested configuration structure for better organization

#### Logging System (`src/core/logger.py`)
- Structured logging with JSON support
- File rotation and console output
- Configurable log levels
- **ENHANCEMENT**: Python JSON logger integration for better log parsing
- **ENHANCEMENT**: Contextual logging with `ContextualLoggerAdapter` for dynamic context (symbol, trade_id, etc.)
- **ENHANCEMENT**: Context variables using `contextvars` for thread-safe logging context

### 2. Data Layer

#### Database (`src/storage/database.py`)
- SQLite with WAL (Write-Ahead Logging) mode
- High-concurrency support
- Async/await pattern for non-blocking operations
- **ENHANCEMENT**: Semaphore-based connection pooling with timeout configuration
- **ENHANCEMENT**: Optimized indexes on frequently queried columns (signals.created_at, trades.entry_time, orders.created_at, klines.open_time)
- **ENHANCEMENT**: Transaction support with context manager for atomic operations
- **ENHANCEMENT**: Chunked batch inserts for efficient bulk operations
- **ENHANCEMENT**: Pagination support with LIMIT and ORDER BY for large result sets

#### Models (`src/storage/models.py`)
- Dataclass-based models for type safety
- Enum types for status fields
- Clean separation of concerns

### 3. API Integration

#### Binance Client (`src/api/binance_client.py`)
- REST API client with retry logic
- WebSocket support for real-time data
- Time synchronization to prevent timestamp errors
- **ENHANCEMENT**: Exponential backoff retry with tenacity
- **ENHANCEMENT**: Automatic time offset calculation
- **ENHANCEMENT**: Circuit breaker pattern to prevent cascading failures
- **ENHANCEMENT**: LRU cache with TTL for `get_klines` (30s) and `get_order_book` (5s)
- **ENHANCEMENT**: Semaphore-based rate limiting and sliding-window rate limiter
- **ENHANCEMENT**: API timeout configuration using constants
- **ENHANCEMENT**: API key masking in `__repr__` for security
- **ENHANCEMENT**: API key validation on initialization

### 4. Technical Analysis

#### Indicators (`src/indicators/technical.py`)
- TA-Lib integration via `ta` library
- EMA, RSI, ADX, Bollinger Bands, ATR
- Signal detection functions for each strategy
- **ENHANCEMENT**: Pandas-based calculations for performance

### 5. Machine Learning

#### Price Predictor (`src/ml/predictor.py`)
- TensorFlow Lite model support
- Feature preparation from klines
- Confidence scoring
- **ENHANCEMENT**: Fallback dummy prediction for development
- **ENHANCEMENT**: Async wrapper that runs synchronous inference in thread pool to prevent blocking event loop

### 6. Risk Management

#### Risk Manager (`src/risk/manager.py`)
- ADX-based chop detection
- ATR-based stop loss calculation
- Position sizing based on risk percentage
- Daily loss limits
- Trade cooldown periods
- Liquidity and spread checks
- Breakeven logic
- Trailing stop management
- **ENHANCEMENT**: Comprehensive validation before trade execution

### 7. Market Scanner

#### Scanner (`src/scanner/scanner.py`)
- Parallel strategy execution
- Kline caching for performance
- Historical warmup
- **ENHANCEMENT**: RAM-based kline buffer using `collections.deque` for efficient O(1) operations
- **ENHANCEMENT**: Cache size limits and TTL-based cleanup to prevent memory leaks
- **ENHANCEMENT**: Base strategy class (`BaseStrategy`) for common functionality and code reuse

#### Strategies (`src/scanner/strategies.py`, `src/scanner/breakout_strategy.py`)
- Trend Strategy: EMA crossover + ADX
- Mean Reversion Strategy: Bollinger Bands + RSI
- Momentum Strategy: RSI + Volume
- Breakout Strategy: Support/resistance breakout detection
- **ENHANCEMENT**: Configurable parameters per strategy
- **ENHANCEMENT**: All strategies inherit from `BaseStrategy` for code reuse
- **ENHANCEMENT**: Standardized error messages with context

### 8. Trading Engine

#### Engine (`src/trading/engine.py`)
- Signal processing and trade execution
- Open trade monitoring
- Stop loss and take profit management
- ML prediction integration
- **ENHANCEMENT**: Unified fill processor for RAM ↔ DB sync
- **ENHANCEMENT**: Integrated `TradeMonitor` for exit condition checking
- **ENHANCEMENT**: Comprehensive error handling with order cancellation on failures
- **ENHANCEMENT**: Contextual logging for better traceability

#### Fill Processor (`src/trading/engine.py`)
- RAM state caching
- Database synchronization
- Trade lifecycle management
- **ENHANCEMENT**: Sub-millisecond state access
- **ENHANCEMENT**: Transaction support for atomic operations

#### Trade Monitor (`src/trading/monitor.py`)
- **NEW**: Dedicated module for monitoring open trades
- Exit condition checking (stop loss, take profit, trailing stop)
- Trailing stop price updates
- **BENEFIT**: Separation of concerns, improved modularity and testability

### 9. Dashboard

#### Dashboard API (`src/dashboard/api.py`)
- FastAPI-based REST API
- WebSocket support for real-time updates
- HTML dashboard with live visualization
- **ENHANCEMENT**: Real-time bot intelligence display
- **ENHANCEMENT**: Restricted CORS origins for security (defaults to localhost)
- **ENHANCEMENT**: Pydantic models for API input validation (`ExportRequest`)

### 10. Main Application

#### Trading Bot (`src/main.py`)
- Component initialization
- Graceful shutdown handling
- Signal processing loop
- **ENHANCEMENT**: Proper async/await patterns throughout
- **ENHANCEMENT**: Refactored initialization into focused `_initialize_*` methods for better modularity
- **ENHANCEMENT**: Atomic signal processing with status tracking to prevent race conditions

### 11. Core Utilities

#### Cache (`src/core/cache.py`)
- **NEW**: LRU cache implementation with TTL support
- Thread-safe caching for API responses
- Automatic expiration cleanup
- **BENEFIT**: Reduces redundant API calls, improves performance

#### Circuit Breaker (`src/core/circuit_breaker.py`)
- **NEW**: Circuit breaker pattern implementation
- Protects against cascading API failures
- Configurable failure threshold and recovery timeout
- **BENEFIT**: Improves system resilience

#### Performance Monitoring (`src/core/performance.py`)
- **NEW**: Performance monitoring utilities
- `async_timed` decorator for measuring async function execution time
- `PerformanceMonitor` class for tracking metrics
- `measure_time` context manager for operation timing
- `parallel_map` for concurrent processing with concurrency limits
- **BENEFIT**: Helps identify bottlenecks and optimize performance

#### Constants (`src/core/constants.py`)
- **NEW**: Centralized constants management
- Eliminates magic numbers throughout codebase
- API timeouts, intervals, thresholds, etc.
- **BENEFIT**: Easier configuration and maintenance

## Data Flow

```
┌─────────────┐
│ Binance API │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│   Scanner   │────▶│   Signals    │
└─────────────┘     └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Risk Manager │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐     ┌─────────────┐
                    │ ML Predictor │────▶│   Engine    │
                    └──────────────┘     └──────┬──────┘
                                                 │
                                                 ▼
                                          ┌─────────────┐
                                          │ Binance API │
                                          └─────────────┘
                                                 │
                                                 ▼
                                          ┌─────────────┐
                                          │  Database   │
                                          └─────────────┘
                                                 │
                                                 ▼
                                          ┌─────────────┐
                                          │  Dashboard  │
                                          └─────────────┘
```

## Performance Optimizations

1. **LRU Cache**: TTL-based caching for Binance API calls (klines: 30s, order books: 5s)
2. **RAM Caching**: Active state cached in memory for sub-ms access
3. **Kline Buffer**: 200 candles cached using `deque` for O(1) append/pop operations
4. **WAL Mode**: SQLite Write-Ahead Logging for high concurrency
5. **Parallel Scanning**: Multiple strategies run concurrently
6. **Connection Pooling**: Semaphore-based database connection pooling
7. **HTTP Connection Pooling**: Reused connections for news sentiment analysis
8. **Async ML Inference**: TensorFlow Lite inference runs in thread pool
9. **Database Indexes**: Optimized indexes on frequently queried columns
10. **Chunked Batch Inserts**: Efficient bulk database operations
11. **Async Operations**: Non-blocking I/O throughout
12. **Rate Limiting**: Semaphore-based concurrency control and sliding-window rate limiting

## Security Features

1. **Environment Variables**: Sensitive data in `.env` file
2. **Testnet Support**: Safe testing environment
3. **Risk Limits**: Multiple layers of risk protection
4. **Input Validation**: Pydantic models for type safety and API endpoint validation
5. **Error Handling**: Comprehensive exception handling with specific exception types
6. **API Key Masking**: `__repr__` methods mask sensitive API keys
7. **API Key Validation**: Explicit validation on Binance client initialization
8. **CORS Restrictions**: Restricted CORS origins (defaults to localhost)
9. **Input Sanitization**: Config loading with key whitelisting and type validation
10. **Config Security**: YAML parsing error handling and environment variable sanitization

## Monitoring & Observability

1. **Health Checks**: Docker and API health endpoints
2. **Structured Logging**: JSON-formatted logs with contextual logging support
3. **Real-Time Dashboard**: WebSocket updates
4. **Stress Testing**: 72-hour automated testing
5. **E2E Test Suite**: Comprehensive end-to-end tests covering all major components
6. **Performance Monitoring**: Built-in performance monitoring utilities
7. **Metrics**: Prometheus-ready (can be extended)
8. **Contextual Logging**: Dynamic context (symbol, trade_id) in log messages for better traceability

## Deployment

### Docker Architecture
- Multi-stage build for ARM64 optimization
- Resource limits for Raspberry Pi
- Volume mounts for persistence
- Health checks configured

### Container Features
- Graceful shutdown handling
- Auto-restart on failure
- Log rotation
- Health monitoring

## Enhancements Made

1. **Error Recovery**: Exponential backoff retry logic with circuit breaker pattern
2. **Time Synchronization**: Binance server time sync
3. **State Management**: Unified fill processor for consistency with transaction support
4. **Performance**: LRU caching, RAM caching, kline buffers, database indexes, chunked batch inserts
5. **Monitoring**: Comprehensive dashboard, health checks, E2E test suite, performance monitoring
6. **Testing**: Automated stress testing framework and comprehensive E2E tests
7. **Documentation**: Extensive README and architecture docs
8. **Configuration**: Flexible YAML + environment variable system with input sanitization
9. **Code Quality**: Contextual logging, type hints, docstring examples, standardized error messages
10. **Modularity**: TradeMonitor extraction, BaseStrategy for code reuse, refactored initialization
11. **Security**: API key masking, CORS restrictions, input validation, config sanitization
12. **Resilience**: Circuit breaker, rate limiting, connection pooling, transaction support

## Scalability Considerations

- **Horizontal Scaling**: Can run multiple scanner instances
- **Database**: Can migrate to PostgreSQL for larger scale
- **Caching**: Redis can be added for distributed caching
- **Message Queue**: RabbitMQ/Kafka for signal processing
- **Load Balancing**: Multiple dashboard instances possible

## Future Enhancements

1. Backtesting framework
2. Additional trading strategies
3. Multi-exchange support
4. Advanced ML models
5. Telegram notifications
6. Performance analytics
7. Portfolio management
8. Strategy backtesting and optimization

---

**Built with production-grade practices and best practices**
