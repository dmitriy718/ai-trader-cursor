"""Multi-strategy market scanner."""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from collections import deque

from ..core.logger import setup_logger
from ..storage.models import Kline, ScannerSignal
from ..api.binance_client import BinanceClient
from ..storage.database import Database
from .strategies import TrendStrategy, MeanReversionStrategy, MomentumStrategy
from .breakout_strategy import BreakoutStrategy


class MarketScanner:
    """Multi-strategy market scanner running in parallel."""
    
    def __init__(
        self,
        binance_client: BinanceClient,
        database: Database,
        symbols: List[str],
        interval_seconds: int = 60,
        trend_config: Optional[Dict] = None,
        mean_reversion_config: Optional[Dict] = None,
        momentum_config: Optional[Dict] = None,
        breakout_config: Optional[Dict] = None
    ):
        """
        Initialize market scanner.
        
        Args:
            binance_client: Binance API client
            database: Database instance
            symbols: List of symbols to scan
            interval_seconds: Scan interval in seconds
            trend_config: Trend strategy configuration
            mean_reversion_config: Mean reversion strategy configuration
            momentum_config: Momentum strategy configuration
        """
        self.binance_client = binance_client
        self.database = database
        self.symbols = symbols
        self.interval_seconds = interval_seconds
        self.logger = setup_logger("MarketScanner")
        
        # Initialize strategies
        trend_config = trend_config or {}
        mean_reversion_config = mean_reversion_config or {}
        momentum_config = momentum_config or {}
        
        self.trend_strategy = TrendStrategy(**trend_config) if trend_config and trend_config.get('enabled', True) else None
        self.mean_reversion_strategy = MeanReversionStrategy(**mean_reversion_config) if mean_reversion_config and mean_reversion_config.get('enabled', True) else None
        self.momentum_strategy = MomentumStrategy(**momentum_config) if momentum_config and momentum_config.get('enabled', True) else None
        self.breakout_strategy = BreakoutStrategy(**breakout_config) if breakout_config and breakout_config.get('enabled', True) else None
        
        self.running = False
        self.kline_cache: Dict[str, deque] = {}
        
        # Import constants
        from ..core.constants import MAX_CACHE_SIZE, CACHE_TTL_SECONDS, CACHE_CLEANUP_INTERVAL
        
        self.cache_max_size = MAX_CACHE_SIZE
        self.cache_ttl_seconds = CACHE_TTL_SECONDS
        self.cache_cleanup_interval = CACHE_CLEANUP_INTERVAL
    
    async def warmup(self, minutes: int = 120):
        """Warm up kline cache with historical data."""
        self.logger.info(f"Warming up kline cache with {minutes} minutes of history...")
        
        for symbol in self.symbols:
            try:
                # Fetch historical klines
                end_time = datetime.now()
                klines = await self.binance_client.get_klines(
                    symbol=symbol,
                    interval="1m",
                    limit=min(200, minutes)  # Binance limit is 1000, but we use 200
                )
                
                if klines:
                    self.kline_cache[symbol] = klines
                    await self.database.insert_klines(klines)
                    self.logger.info(f"Warmed up {symbol}: {len(klines)} klines")
            except (ConnectionError, TimeoutError) as e:
                self.logger.error(f"Network error warming up {symbol}: {e}")
            except (ValueError, KeyError) as e:
                self.logger.error(f"Data error warming up {symbol}: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error warming up {symbol}: {e}", exc_info=True)
        
        self.logger.info("Warmup complete")
    
    async def scan_symbol(self, symbol: str) -> List[ScannerSignal]:
        """
        Scan a single symbol with all strategies.
        
        Args:
            symbol: Trading pair symbol
        
        Returns:
            List of detected signals
        """
        signals = []
        
        try:
            # Get klines from cache or fetch new
            klines = self.kline_cache.get(symbol, [])
            
            if not klines:
                # Fetch fresh klines if cache is empty
                klines = await self.binance_client.get_klines(
                    symbol=symbol,
                    interval="1m",
                    limit=200
                )
                if klines:
                    self.kline_cache[symbol] = klines
            
            from ..core.constants import MIN_KLINES_FOR_SCAN
            
            if len(klines) < MIN_KLINES_FOR_SCAN:
                return signals
            
            # Run strategies in parallel
            tasks = []
            
            if self.trend_strategy:
                tasks.append(self.trend_strategy.scan(symbol, klines))
            
            if self.mean_reversion_strategy:
                tasks.append(self.mean_reversion_strategy.scan(symbol, klines))
            
            if self.momentum_strategy:
                tasks.append(self.momentum_strategy.scan(symbol, klines))
            
            if self.breakout_strategy:
                tasks.append(self.breakout_strategy.scan(symbol, klines))
            
            # Execute strategies
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Strategy error: {result}")
                elif result is not None:
                    signals.append(result)
        
        except (ValueError, KeyError, IndexError) as e:
            self.logger.error(f"Data error scanning {symbol}: {e}")
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Network error scanning {symbol}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error scanning {symbol}: {e}", exc_info=True)
        
        return signals
    
    async def update_kline_cache(self, symbol: str, kline: Kline) -> None:
        """
        Update kline cache with new kline data.
        
        Implements TTL and size limits to prevent memory leaks.
        Uses deque for efficient operations.
        
        Example:
            >>> await scanner.update_kline_cache("BTCUSDT", kline)
        """
        if symbol not in self.kline_cache:
            # Use deque with maxlen for automatic size limiting
            self.kline_cache[symbol] = deque(maxlen=self.cache_max_size)
        
        cache = self.kline_cache[symbol]
        now = datetime.now()
        
        # Remove expired entries (older than TTL)
        # Convert to list, filter, then recreate deque
        valid_klines = [
            k for k in cache
            if (now - k.open_time).total_seconds() < self.cache_ttl_seconds
        ]
        
        # Recreate deque with valid klines (maxlen will enforce size limit)
        self.kline_cache[symbol] = deque(valid_klines, maxlen=self.cache_max_size)
        
        # Add new kline (deque will automatically limit size)
        self.kline_cache[symbol].append(kline)
        
        # Periodic cleanup: remove symbols with empty cache
        if len(self.kline_cache[symbol]) == 0:
            self.kline_cache.pop(symbol, None)
    
    async def cleanup_cache(self) -> None:
        """
        Periodic cache cleanup to prevent memory leaks.
        
        Example:
            >>> await scanner.cleanup_cache()
        """
        now = datetime.now()
        symbols_to_remove = []
        
        for symbol, cache in self.kline_cache.items():
            # Remove expired entries (deque supports iteration)
            valid_klines = [
                k for k in cache
                if (now - k.open_time).total_seconds() < self.cache_ttl_seconds
            ]
            
            # Recreate deque with valid klines
            self.kline_cache[symbol] = deque(valid_klines, maxlen=self.cache_max_size)
            
            # Remove empty caches
            if len(self.kline_cache[symbol]) == 0:
                symbols_to_remove.append(symbol)
        
        for symbol in symbols_to_remove:
            self.kline_cache.pop(symbol, None)
        
        if symbols_to_remove:
            self.logger.debug(f"Cleaned up {len(symbols_to_remove)} empty cache entries")
    
    async def scan_all(self) -> List[ScannerSignal]:
        """Scan all symbols in parallel."""
        self.logger.debug(f"Starting scan of {len(self.symbols)} symbols...")
        
        # Scan all symbols in parallel
        tasks = [self.scan_symbol(symbol) for symbol in self.symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_signals = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Error scanning {self.symbols[i]}: {result}")
            elif isinstance(result, list):
                all_signals.extend(result)
        
        if all_signals:
            self.logger.info(f"Detected {len(all_signals)} signals")
            # Store signals in database
            for signal in all_signals:
                try:
                    await self.database.insert_signal(signal)
                except (ValueError, TypeError) as e:
                    self.logger.error(f"Data validation error storing signal: {e}")
                except Exception as e:
                    self.logger.error(f"Database error storing signal: {e}", exc_info=True)
        
        return all_signals
    
    async def run(self):
        """Run scanner in a loop."""
        self.running = True
        self.logger.info(f"Scanner started: scanning {len(self.symbols)} symbols every {self.interval_seconds}s")
        
        cleanup_counter = 0
        
        while self.running:
            try:
                await self.scan_all()
                
                # Periodic cache cleanup to prevent memory leaks
                cleanup_counter += 1
                if cleanup_counter >= self.cache_cleanup_interval:
                    await self.cleanup_cache()
                    cleanup_counter = 0
                
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except (ConnectionError, TimeoutError) as e:
                self.logger.error(f"Network error in scanner loop: {e}")
                await asyncio.sleep(self.interval_seconds)
            except Exception as e:
                self.logger.error(f"Unexpected error in scanner loop: {e}", exc_info=True)
                await asyncio.sleep(self.interval_seconds)
    
    def stop(self):
        """Stop the scanner."""
        self.running = False
        self.logger.info("Scanner stopped")
