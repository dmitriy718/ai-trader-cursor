"""Main application entry point."""

import asyncio
import signal
import sys
from pathlib import Path

from .core.config import load_config
from .core.logger import setup_logger
from .core.notifications import NotificationManager
from .storage.database import Database
from .api.binance_client import BinanceClient
from .risk.manager import RiskManager
from .ml.predictor import PricePredictor
from .scanner.scanner import MarketScanner
from .trading.engine import TradingEngine
from .dashboard.api import DashboardAPI


class TradingBot:
    """Main trading bot application."""
    
    def __init__(self, config_path: str = None):
        """Initialize trading bot."""
        self.config = load_config(config_path)
        self.logger = setup_logger(
            "TradingBot",
            log_file=self.config.logging.file,
            level=self.config.logging.level
        )
        
        self.database: Database = None
        self.binance_client: BinanceClient = None
        self.risk_manager: RiskManager = None
        self.price_predictor: PricePredictor = None
        self.scanner: MarketScanner = None
        self.trading_engine: TradingEngine = None
        self.dashboard: DashboardAPI = None
        self.notification_manager: NotificationManager = None
        
        self.running = False
    
    async def initialize(self):
        """Initialize all components."""
        try:
            self.logger.info("Initializing trading bot...")
            
            await self._initialize_database()
            await self._initialize_binance_client()
            await self._initialize_risk_manager()
            await self._initialize_ml_predictor()
            await self._initialize_notification_manager()
            await self._initialize_scanner()
            await self._initialize_trading_engine()
            await self._initialize_dashboard()
            
            self.logger.info("Trading bot initialization complete")
        
        except Exception as e:
            self.logger.error(f"Error initializing bot: {e}")
            raise
    
    async def _initialize_database(self):
        """Initialize database connection."""
        self.database = Database(
            db_path=self.config.database.path,
            wal_mode=self.config.database.wal_mode
        )
        await self.database.initialize()
        self.logger.info("Database initialized")
    
    async def _initialize_binance_client(self):
        """Initialize Binance API client."""
        self.binance_client = BinanceClient(
            api_key=self.config.binance_api_key,
            api_secret=self.config.binance_api_secret,
            testnet=self.config.binance_testnet
        )
        await self.binance_client.initialize()
        self.logger.info("Binance client initialized")
    
    async def _initialize_risk_manager(self):
        """Initialize risk management system."""
        self.risk_manager = RiskManager(
            risk_per_trade=self.config.trading.risk_per_trade,
            max_position_size_usd=self.config.trading.max_position_size_usd,
            daily_loss_limit_usd=self.config.trading.daily_loss_limit_usd,
            trade_cooldown_seconds=self.config.trading.trade_cooldown_seconds,
            adx_chop_threshold=self.config.risk_management.adx_chop_threshold,
            atr_multiplier=self.config.risk_management.atr_multiplier,
            max_spread_percent=self.config.risk_management.liquidity.max_spread_percent,
            min_book_liquidity_usd=self.config.risk_management.liquidity.min_book_liquidity_usd,
            order_book_imbalance_threshold=self.config.risk_management.liquidity.order_book_imbalance_threshold
        )
        self.logger.info("Risk manager initialized")
    
    async def _initialize_ml_predictor(self):
        """Initialize ML price predictor."""
        self.price_predictor = PricePredictor(
            model_path=self.config.ml.model_path
        )
        self.logger.info("ML predictor initialized")
    
    async def _initialize_notification_manager(self):
        """Initialize notification manager."""
        import os
        self.notification_manager = NotificationManager(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            enabled=os.getenv("NOTIFICATIONS_ENABLED", "false").lower() == "true"
        )
        self.logger.info("Notification manager initialized")
    
    async def _initialize_scanner(self):
        """Initialize market scanner."""
        self.scanner = MarketScanner(
            binance_client=self.binance_client,
            database=self.database,
            symbols=self.config.scanner.symbols,
            interval_seconds=self.config.scanner.interval_seconds,
            trend_config={
                'enabled': True,
                'ema_fast': self.config.scanner.trend.ema_fast,
                'ema_slow': self.config.scanner.trend.ema_slow,
                'adx_threshold': self.config.scanner.trend.adx_threshold
            },
            mean_reversion_config={
                'enabled': True,
                'bollinger_period': self.config.scanner.mean_reversion.bollinger_period,
                'bollinger_std': self.config.scanner.mean_reversion.bollinger_std,
                'rsi_period': self.config.scanner.mean_reversion.rsi_period,
                'rsi_oversold': self.config.scanner.mean_reversion.rsi_oversold
            },
            momentum_config={
                'enabled': True,
                'rsi_period': self.config.scanner.momentum.rsi_period,
                'rsi_threshold': self.config.scanner.momentum.rsi_threshold,
                'volume_multiplier': self.config.scanner.momentum.volume_multiplier
            },
            breakout_config={
                'enabled': True,
                'consolidation_periods': 20,
                'breakout_threshold_percent': 1.0,
                'volume_multiplier': 1.5
            }
        )
        
        # Warm up scanner
        await self.scanner.warmup(minutes=self.config.performance.historical_warmup_minutes)
        self.logger.info("Scanner initialized")
    
    async def _initialize_trading_engine(self):
        """Initialize trading engine."""
        self.trading_engine = TradingEngine(
            binance_client=self.binance_client,
            database=self.database,
            risk_manager=self.risk_manager,
            price_predictor=self.price_predictor,
            notification_manager=self.notification_manager,
            trading_enabled=self.config.trading.enabled
        )
        self.logger.info("Trading engine initialized")
    
    async def _initialize_dashboard(self):
        """Initialize dashboard API."""
        self.dashboard = DashboardAPI(
            database=self.database,
            trading_engine=self.trading_engine,
            scanner=self.scanner,
            host=self.config.api.host,
            port=self.config.api.port,
            cors_origins=self.config.api.cors_origins
        )
        self.logger.info("Dashboard initialized")
    
    async def run(self):
        """Run the trading bot."""
        self.running = True
        self.logger.info("Starting trading bot...")
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Start dashboard in background
            dashboard_task = asyncio.create_task(self.dashboard.run())
            
            # Start scanner
            scanner_task = asyncio.create_task(self.scanner.run())
            
            # Start trading engine monitoring
            trading_task = asyncio.create_task(self.trading_engine.run())
            
            # Start signal processing loop
            signal_task = asyncio.create_task(self._process_signals_loop())
            
            # Wait for all tasks
            await asyncio.gather(
                dashboard_task,
                scanner_task,
                trading_task,
                signal_task,
                return_exceptions=True
            )
        
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def _process_signals_loop(self):
        """Process scanner signals in a loop."""
        from ..core.constants import DEFAULT_SCAN_INTERVAL_SECONDS
        
        while self.running:
            try:
                # Reset stuck signals (older than timeout)
                await self.database.reset_stuck_signals()
                
                # Get unprocessed signals
                signals = await self.database.get_unprocessed_signals()
                
                for signal in signals:
                    if not self.running:
                        break
                    
                    # Atomically mark as processing to prevent race conditions
                    if await self.database.mark_signal_processing(signal.signal_id):
                        try:
                            await self.trading_engine.process_signal(signal)
                            # Mark as processed only after successful processing
                            await self.database.mark_signal_processed(signal.signal_id)
                        except Exception as e:
                            # Mark as failed if processing throws an error
                            error_msg = str(e)[:500]  # Limit error message length
                            await self.database.mark_signal_failed(signal.signal_id, error_msg)
                            self.logger.error(
                                f"Error processing signal {signal.signal_id} ({signal.symbol}): {e}"
                            )
                
                # Sleep before next iteration
                await asyncio.sleep(5)  # Process signals every 5 seconds
            
            except Exception as e:
                self.logger.error(f"Error in signal processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def shutdown(self):
        """Shutdown bot gracefully."""
        self.logger.info("Shutting down trading bot...")
        self.running = False
        
        if self.scanner:
            self.scanner.stop()
        
        if self.trading_engine:
            self.trading_engine.stop()
        
        if self.binance_client:
            await self.binance_client.close()
        
        if self.database:
            await self.database.close()
        
        self.logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    bot = TradingBot()
    try:
        await bot.initialize()
        await bot.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
