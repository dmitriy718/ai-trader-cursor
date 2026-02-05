# Quick Start Guide

Get your AI Trading Bot up and running in 5 minutes!

## Prerequisites

- Docker and Docker Compose installed
- Binance API credentials (get them from https://www.binance.com/en/my/settings/api-management)

## Step 1: Setup

```bash
# Run the setup script
make setup
# or
bash scripts/setup.sh
```

## Step 2: Configure

Edit `.env` file and add your Binance API credentials:

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true  # Start with testnet!
TRADING_ENABLED=false  # Keep disabled until you're ready
```

## Step 3: Build and Run

```bash
# Build the Docker image
make build

# Start the bot
make up

# View logs
make logs
```

## Step 4: Access Dashboard

Open your browser:
```
http://localhost:8000
```

## Step 5: Test (Optional)

Run E2E tests to verify everything works:

```bash
# Install test dependencies
pip install -r requirements.txt

# Run E2E tests
pytest tests/e2e/ -v

# Or run a 1-hour stress test
make test
```

## Important Notes

1. **Always start with testnet**: Set `BINANCE_TESTNET=true` in `.env`
2. **Keep trading disabled initially**: Set `TRADING_ENABLED=false` until you've tested thoroughly
3. **Monitor the logs**: Watch for any errors or warnings
4. **Start small**: When ready for live trading, use small position sizes

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs trading-bot

# Verify API credentials
cat .env | grep BINANCE
```

### No signals detected
- Verify symbols in `config/config.yaml`
- Check Binance API connectivity
- Review scanner logs

### Dashboard not accessible
- Verify port 8000 is not in use: `lsof -i :8000`
- Check container is running: `docker ps`

## Next Steps

1. Review `config/config.yaml` to customize trading parameters
2. Monitor the dashboard for a few hours
3. Review logs for any issues
4. When confident, enable testnet trading: `TRADING_ENABLED=true`
5. After successful testnet testing, switch to live (carefully!)

## Safety Checklist

Before enabling live trading:

- [ ] Tested on testnet for at least 24 hours
- [ ] Reviewed and understood all risk parameters
- [ ] Set appropriate daily loss limits
- [ ] Verified API key permissions (read-only + trade, no withdraw)
- [ ] Started with minimal position sizes
- [ ] Have monitoring in place
- [ ] Understand the risks involved

---

**Remember**: Trading involves risk. Never invest more than you can afford to lose!
