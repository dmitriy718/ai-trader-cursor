# AI Trading Bot - Production-Ready Crypto Trading System

A production-ready, AI-powered cryptocurrency trading bot for Binance with self-improving capabilities, advanced risk management, and comprehensive monitoring.

## 🚀 Features

### Core Capabilities
- **Multi-Strategy Scanner**: Trend following, mean reversion, and momentum strategies running in parallel
- **ML Price Prediction**: TensorFlow Lite-based price prediction with confidence scoring
- **Advanced Risk Management**: ADX chop detection, ATR-based trailing stops, breakeven logic
- **Real-Time Dashboard**: FastAPI-based dashboard with WebSocket updates
- **Production Hardened**: Graceful shutdown, error recovery, health checks, stress testing

### Risk Management
- **ADX-Based Chop Detection**: Avoids trading in sideways markets
- **ATR Trailing Stop Loss**: Dynamic stop loss based on volatility
- **Breakeven Logic**: Automatically moves stop loss to breakeven after profit threshold
- **Bankroll Controls**: Percentage-based risk per trade, daily loss limits, position size caps
- **Liquidity Guards**: Order book imbalance detection, spread limits, minimum liquidity enforcement

### Performance Optimizations
- **LRU Cache**: TTL-based caching for API calls (klines, order books) to reduce redundant requests
- **RAM Caching**: Sub-millisecond access to active state
- **Kline Buffer**: 200 candles cached in memory using `deque` for efficient operations
- **Unified Fill Processor**: Synchronizes RAM state with database
- **Circuit Breaker**: Protects against cascading API failures
- **Connection Pooling**: HTTP connection pooling for news sentiment analysis
- **Async ML Inference**: TensorFlow Lite inference runs in thread pool to prevent blocking
- **Exponential Backoff**: Retry logic with exponential backoff on failures
- **Binance Time Sync**: Prevents timestamp drift errors
- **Database Indexes**: Optimized indexes for common queries
- **Chunked Batch Inserts**: Efficient batch database operations

### Monitoring & Testing
- **E2E Test Suite**: Comprehensive end-to-end tests covering trading flow, scanner, dashboard, database, risk management, and performance
- **72-Hour Stress Tester**: Automated stress testing with container restart monitoring
- **Health Checks**: Docker health checks and API endpoints
- **Real-Time Dashboard**: Live visualization of bot status, trades, and signals
- **Comprehensive Logging**: Structured logging with contextual logging support and rotation
- **Performance Monitoring**: Built-in performance monitoring utilities with timing decorators

## 📋 Requirements

- Python 3.11+
- Docker & Docker Compose
- Binance API credentials (API key and secret)
- ARM64 compatible system (Raspberry Pi 4+ recommended) or x86_64

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ai-trading-bot
```

### 2. Configure Environment

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` and set your Binance API credentials:

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true  # Set to false for live trading
TRADING_ENABLED=false  # Set to true to enable live trading
```

### 3. Review Configuration

Edit `config/config.yaml` to customize:
- Trading parameters (risk per trade, position sizes, etc.)
- Scanner settings (symbols, intervals, strategy parameters)
- Risk management thresholds
- API server settings

### 4. Build and Run with Docker

```bash
# Build the Docker image
docker-compose build

# Start the bot
docker-compose up -d

# View logs
docker-compose logs -f trading-bot

# Stop the bot
docker-compose down
```

### 5. Access Dashboard

Open your browser and navigate to:
```
http://localhost:8000
```

The dashboard provides:
- Real-time bot status
- Open trades and PnL
- Scanner signals
- Strategy status indicators

## 📊 Usage

### Running the Bot

#### Development Mode (Local)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python -m src.main --config config/config.yaml
```

#### Production Mode (Docker)

```bash
docker-compose up -d
```

### Stress Testing

Run the 72-hour stress test:

```bash
python scripts/stress_test.py --duration 72
```

The stress tester will:
- Monitor container health
- Detect freezes and crashes
- Automatically restart containers
- Generate a comprehensive report

### Monitoring

#### Health Check Endpoint

```bash
curl http://localhost:8000/api/health
```

#### Statistics Endpoint

```bash
curl http://localhost:8000/api/stats
```

#### WebSocket Updates

Connect to `ws://localhost:8000/ws` for real-time updates.

## 🏗️ Architecture

### Project Structure

```
ai-trading-bot/
├── src/
│   ├── api/              # Binance API client
│   ├── core/              # Configuration and logging
│   ├── dashboard/         # FastAPI dashboard
│   ├── indicators/        # Technical indicators
│   ├── ml/                # ML prediction module
│   ├── risk/              # Risk management
│   ├── scanner/           # Market scanner strategies
│   ├── storage/           # Database models and operations
│   ├── trading/           # Trading engine
│   └── main.py            # Application entry point
├── config/                # Configuration files
├── scripts/               # Utility scripts
├── tests/                 # Test files
├── docker/                # Docker-related files
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose configuration
└── requirements.txt       # Python dependencies
```

### Component Overview

1. **Market Scanner**: Scans multiple symbols with multiple parallel strategies (Trend, Mean Reversion, Momentum, Breakout)
2. **Risk Manager**: Validates all trades before execution with comprehensive checks
3. **Trading Engine**: Executes trades and manages positions with unified fill processing
4. **Trade Monitor**: Monitors open trades and manages exit conditions (stop loss, take profit, trailing stops)
5. **ML Predictor**: Enhances signal confidence with price predictions (async TensorFlow Lite)
6. **Dashboard**: Real-time monitoring and visualization with WebSocket support
7. **Database**: SQLite with WAL mode, connection pooling, and optimized indexes
8. **Cache Layer**: LRU cache with TTL for API call optimization
9. **Circuit Breaker**: Protects against cascading API failures

### Data Flow

```
Market Data → Scanner → Signals → Risk Manager → Trading Engine → Binance API
                                      ↓
                                 ML Predictor
                                      ↓
                                 Dashboard
```

## ⚙️ Configuration

### Trading Configuration

Key parameters in `config/config.yaml`:

```yaml
trading:
  risk_per_trade: 0.02          # 2% risk per trade
  max_position_size_usd: 1000.0 # Maximum position size
  daily_loss_limit_usd: 100.0   # Daily loss limit
  trade_cooldown_seconds: 300     # Cooldown between trades
```

### Scanner Configuration

```yaml
scanner:
  interval_seconds: 60           # Scan interval
  symbols:                        # Symbols to scan
    - BTCUSDT
    - ETHUSDT
    # ... more symbols
```

### Risk Management

```yaml
risk_management:
  adx_chop_threshold: 25.0       # ADX threshold for trend detection
  atr_multiplier: 2.0            # ATR multiplier for stop loss
  max_spread_percent: 0.5        # Maximum bid/ask spread
```

## 🔒 Security Best Practices

1. **Never commit API keys**: Keep `.env` file out of version control (see `SECURITY.md`)
2. **Use testnet first**: Test thoroughly on Binance testnet before live trading
3. **Start with small amounts**: Begin with minimal position sizes
4. **Monitor daily limits**: Set appropriate daily loss limits
5. **Regular backups**: Backup database files regularly
6. **Review `.gitignore`**: Ensure all secrets are protected (see `.gitignore` and `SECURITY.md`)

**📖 For detailed security guidelines, see [SECURITY.md](SECURITY.md)**

## 🧪 Testing

### E2E Tests

Comprehensive end-to-end test suite covering all major components:

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run specific test suites
pytest tests/e2e/test_trading_flow.py -v
pytest tests/e2e/test_scanner_flow.py -v
pytest tests/e2e/test_dashboard_api.py -v
pytest tests/e2e/test_database_operations.py -v
pytest tests/e2e/test_risk_management.py -v
pytest tests/e2e/test_performance.py -v
pytest tests/e2e/test_integration_full_flow.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Unit Tests

```bash
pytest tests/ -v
```

### Integration Tests

```bash
# Run with testnet
BINANCE_TESTNET=true python -m src.main
```

### Stress Test

```bash
python scripts/stress_test.py --duration 72
```

## 📈 Performance

### Optimizations

- **LRU Cache**: TTL-based caching for Binance API calls (30s for klines, 5s for order books)
- **RAM Caching**: Active state cached in memory for sub-ms access
- **Kline Buffer**: 200 candles cached using `deque` for O(1) operations
- **Parallel Scanning**: Multiple strategies run concurrently
- **WAL Mode**: SQLite Write-Ahead Logging for high concurrency
- **Connection Pooling**: Efficient database connection management with semaphore-based pooling
- **HTTP Connection Pooling**: Reused connections for news sentiment analysis
- **Async ML Inference**: Non-blocking TensorFlow Lite inference in thread pool
- **Circuit Breaker**: Prevents cascading failures from API issues
- **Database Indexes**: Optimized indexes on frequently queried columns
- **Chunked Batch Inserts**: Efficient bulk database operations
- **Rate Limiting**: Semaphore-based concurrency control and sliding-window rate limiting

### Resource Usage (Raspberry Pi 4)

- **CPU**: ~20-30% average
- **Memory**: ~500MB-1GB
- **Disk**: ~100MB (database + logs)
- **Network**: Minimal (API calls only)

## 🐛 Troubleshooting

### Container Won't Start

1. Check Docker logs: `docker-compose logs trading-bot`
2. Verify API credentials in `.env`
3. Ensure ports 8000 is available
4. Check disk space: `df -h`

### No Signals Detected

1. Verify symbols are correct in config
2. Check Binance API connectivity
3. Review scanner logs for errors
4. Ensure sufficient historical data (warmup period)

### Trading Not Executing

1. Verify `TRADING_ENABLED=true` in `.env`
2. Check account balance
3. Review risk management logs
4. Ensure daily loss limit not reached

## 📝 Logging

Logs are written to:
- **File**: `/app/logs/trading_bot.log` (inside container)
- **Console**: Docker logs via `docker-compose logs`

Log levels can be configured in `config/config.yaml`:
- `DEBUG`: Detailed debugging information
- `INFO`: General information (default)
- `WARNING`: Warning messages
- `ERROR`: Error messages

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is provided as-is for educational and research purposes. Use at your own risk.

## ⚠️ Disclaimer

**Trading cryptocurrencies involves substantial risk of loss. This bot is provided for educational purposes only. Past performance does not guarantee future results. Always:**

- Test thoroughly on testnet before live trading
- Start with small amounts
- Monitor your bot regularly
- Understand the risks involved
- Never invest more than you can afford to lose

## 🆘 Support

For issues and questions:
1. Check the logs first
2. Review the configuration
3. Consult the troubleshooting section
4. Open an issue on GitHub

## 🎯 Roadmap

- [x] Additional trading strategies (Breakout strategy added)
- [x] Backtesting framework (Implemented)
- [x] Telegram notifications (Implemented)
- [x] Performance analytics dashboard (Implemented)
- [x] E2E test suite (Comprehensive coverage)
- [x] Caching layer (LRU cache with TTL)
- [x] Circuit breaker pattern (API resilience)
- [ ] Advanced ML models
- [ ] Multi-exchange support
- [ ] Strategy optimization framework
- [ ] Advanced portfolio management

---

**Built with ❤️ for the crypto trading community**
