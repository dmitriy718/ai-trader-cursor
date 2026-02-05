"""Binance API client with REST and WebSocket support."""

import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException, BinanceRequestException, BinanceOrderException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiohttp

from ..core.logger import setup_logger
from ..storage.models import Kline, Order, OrderSide, OrderStatus, OrderType


class BinanceClient:
    """Binance API client with time synchronization and retry logic."""
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False
    ):
        """
        Initialize Binance client.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet environment
        
        Example:
            >>> client = BinanceClient(api_key="...", api_secret="...", testnet=True)
            >>> await client.initialize()
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.client: Optional[AsyncClient] = None
        self.socket_manager: Optional[BinanceSocketManager] = None
        self.logger = setup_logger("BinanceClient")
        self._time_offset = 0
        self._ws_connections: Dict[str, Any] = {}
    
    def __repr__(self) -> str:
        """String representation that masks API keys."""
        return f"BinanceClient(testnet={self.testnet}, api_key=***)"
        
        # Rate limiting: Binance allows 1200 requests per minute
        from ..core.constants import (
            DEFAULT_RATE_LIMIT_WINDOW,
            DEFAULT_MAX_REQUESTS_PER_WINDOW,
            DEFAULT_CONCURRENT_REQUESTS
        )
        
        # Use semaphore to limit concurrent requests
        self._rate_limiter = asyncio.Semaphore(DEFAULT_CONCURRENT_REQUESTS)
        self._request_times: List[float] = []  # Track request times for rate limiting
        self._rate_limit_window = DEFAULT_RATE_LIMIT_WINDOW
        self._max_requests_per_window = DEFAULT_MAX_REQUESTS_PER_WINDOW
        
        # Circuit breaker for API resilience
        from ..core.circuit_breaker import CircuitBreaker, CircuitOpenError
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=(BinanceAPIException, BinanceRequestException, ConnectionError, TimeoutError, aiohttp.ClientError),
            name="BinanceAPI"
        )
        
        # Circuit breaker for API resilience
        from ..core.circuit_breaker import CircuitBreaker, CircuitOpenError
        from binance.exceptions import BinanceAPIException, BinanceRequestException
        
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=(BinanceAPIException, BinanceRequestException, ConnectionError, TimeoutError),
            name="BinanceAPI"
        )
    
    async def initialize(self):
        """Initialize Binance client and sync time."""
        # Validate API credentials before attempting connection
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Binance API key and secret are required. "
                "Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables."
            )
        
        if len(self.api_key) < 10 or len(self.api_secret) < 10:
            raise ValueError(
                "Invalid API credentials: API key and secret must be at least 10 characters long."
            )
        
        try:
            self.client = await AsyncClient.create(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            self.socket_manager = BinanceSocketManager(self.client)
            
            # Test connection by fetching account info (validates credentials)
            try:
                account = await self.client.get_account()
                self.logger.info(f"Binance API credentials validated successfully (testnet={self.testnet})")
            except BinanceAPIException as e:
                if e.code == -2015:  # Invalid API-key, IP, or permissions
                    raise ValueError(
                        f"Invalid Binance API credentials or insufficient permissions: {e.message}"
                    )
                raise
            
            await self._sync_time()
            self.logger.info("Binance client initialized")
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Binance client: {e}")
            raise ValueError(f"Failed to connect to Binance API: {e}") from e
    
    async def close(self):
        """Close all connections."""
        # Close WebSocket connections
        for symbol, ws in self._ws_connections.items():
            try:
                await ws.close()
            except (ConnectionError, asyncio.CancelledError, RuntimeError) as e:
                self.logger.warning(f"Error closing WebSocket for {symbol}: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error closing WebSocket for {symbol}: {e}", exc_info=True)
        
        if self.client:
            try:
                await self.client.close_connection()
            except (ConnectionError, RuntimeError) as e:
                self.logger.warning(f"Error closing Binance client connection: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error closing client: {e}", exc_info=True)
    
    async def _sync_time(self):
        """Sync local time with Binance server time."""
        try:
            server_time = await self.client.get_server_time()
            local_time = int(time.time() * 1000)
            self._time_offset = server_time['serverTime'] - local_time
            self.logger.info(f"Time offset synchronized: {self._time_offset}ms")
        except (BinanceAPIException, BinanceRequestException, ConnectionError, TimeoutError) as e:
            self.logger.warning(f"Failed to sync time: {e}")
            self._time_offset = 0
        except Exception as e:
            self.logger.error(f"Unexpected error syncing time: {e}", exc_info=True)
            self._time_offset = 0
    
    def _get_server_time(self) -> int:
        """Get current server time."""
        return int(time.time() * 1000) + self._time_offset
    
    async def _check_rate_limit(self):
        """
        Check and enforce rate limiting.
        
        Removes requests older than the time window and waits if limit exceeded.
        """
        now = time.time()
        
        # Remove requests outside the time window
        self._request_times[:] = [
            t for t in self._request_times
            if now - t < self._rate_limit_window
        ]
        
        # If we're at the limit, wait until oldest request expires
        if len(self._request_times) >= self._max_requests_per_window:
            oldest_request = min(self._request_times)
            wait_time = self._rate_limit_window - (now - oldest_request) + 0.1
            if wait_time > 0:
                self.logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                # Re-check after waiting
                now = time.time()
                self._request_times[:] = [
                    t for t in self._request_times
                    if now - t < self._rate_limit_window
                ]
        
        # Record this request
        self._request_times.append(now)
    
    async def _rate_limited_request(self, coro):
        """
        Execute a request with rate limiting, timeout, and circuit breaker protection.
        
        Args:
            coro: Coroutine to execute
        
        Returns:
            Result of the coroutine
        
        Raises:
            asyncio.TimeoutError: If request exceeds timeout
            CircuitOpenError: If circuit breaker is open
        """
        from ..core.constants import DEFAULT_API_TIMEOUT_SECONDS
        
        # Wrap with circuit breaker
        async def _execute():
            # Acquire semaphore for concurrency control
            async with self._rate_limiter:
                # Check and enforce rate limit
                await self._check_rate_limit()
                
                # Execute the request with timeout
                return await asyncio.wait_for(coro, timeout=DEFAULT_API_TIMEOUT_SECONDS)
        
        try:
            return await self._circuit_breaker.call(_execute)
        except asyncio.TimeoutError:
            self.logger.error(f"API request timed out after {DEFAULT_API_TIMEOUT_SECONDS} seconds")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            BinanceAPIException,
            BinanceRequestException,
            ConnectionError,
            TimeoutError,
            aiohttp.ClientError
        ))
    )
    @cached_async(ttl_seconds=30, max_size=1000)  # Cache for 30 seconds
    async def get_klines(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 200,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """
        Get klines (candlestick data) for a symbol.
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval (1m, 5m, 1h, etc.)
            limit: Number of klines to retrieve
            end_time: End time for klines
        
        Returns:
            List of Kline objects
        """
        try:
            end_ms = None
            if end_time:
                end_ms = int(end_time.timestamp() * 1000)
            
            # Execute with rate limiting
            klines = await self._rate_limited_request(
                self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit,
                    endTime=end_ms
                )
            )
            
            return [
                Kline(
                    symbol=symbol,
                    open_time=datetime.fromtimestamp(k[0] / 1000),
                    close_time=datetime.fromtimestamp(k[6] / 1000),
                    open_price=float(k[1]),
                    high_price=float(k[2]),
                    low_price=float(k[3]),
                    close_price=float(k[4]),
                    volume=float(k[5]),
                    quote_volume=float(k[7]),
                    trades=int(k[8]),
                    taker_buy_base_volume=float(k[9]),
                    taker_buy_quote_volume=float(k[10])
                )
                for k in klines
            ]
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error fetching klines for {symbol}: {e}")
            raise
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error fetching klines for {symbol}: {e}")
            raise
        except (KeyError, ValueError, IndexError) as e:
            self.logger.error(f"Data parsing error for klines {symbol}: {e}")
            raise ValueError(f"Invalid kline data format: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error fetching klines for {symbol}: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            BinanceAPIException,
            BinanceRequestException,
            ConnectionError,
            TimeoutError,
            aiohttp.ClientError
        ))
    )
    @cached_async(ttl_seconds=5, max_size=500)  # Cache for 5 seconds (order book changes frequently)
    async def get_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Trading pair symbol
            limit: Number of bids/asks to retrieve
        
        Returns:
            Order book data
        """
        try:
            # Execute with rate limiting
            book = await self._rate_limited_request(
                self.client.get_order_book(symbol=symbol, limit=limit)
            )
            
            bids = [(float(b[0]), float(b[1])) for b in book['bids']]
            asks = [(float(a[0]), float(a[1])) for a in book['asks']]
            
            best_bid = bids[0][0] if bids else 0
            best_ask = asks[0][0] if asks else 0
            spread = best_ask - best_bid if best_ask and best_bid else 0
            spread_percent = (spread / best_bid * 100) if best_bid else 0
            
            # Calculate order book imbalance
            bid_volume = sum(price * qty for price, qty in bids)
            ask_volume = sum(price * qty for price, qty in asks)
            total_volume = bid_volume + ask_volume
            imbalance = (bid_volume - ask_volume) / total_volume if total_volume > 0 else 0
            
            # Calculate liquidity (sum of top 5 levels)
            top_bid_liquidity = sum(price * qty for price, qty in bids[:5])
            top_ask_liquidity = sum(price * qty for price, qty in asks[:5])
            min_liquidity = min(top_bid_liquidity, top_ask_liquidity)
            
            return {
                'symbol': symbol,
                'bids': bids,
                'asks': asks,
                'best_bid': best_bid,
                'best_ask': best_ask,
                'spread': spread,
                'spread_percent': spread_percent,
                'imbalance': imbalance,
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'min_liquidity_usd': min_liquidity
            }
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error fetching order book for {symbol}: {e}")
            raise
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error fetching order book for {symbol}: {e}")
            raise
        except (KeyError, ValueError, IndexError) as e:
            self.logger.error(f"Data parsing error for order book {symbol}: {e}")
            raise ValueError(f"Invalid order book data format: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error fetching order book for {symbol}: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            BinanceAPIException,
            BinanceRequestException,
            ConnectionError,
            TimeoutError,
            aiohttp.ClientError
        ))
    )
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24h ticker statistics."""
        try:
            # Execute with rate limiting
            ticker = await self._rate_limited_request(
                self.client.get_ticker(symbol=symbol)
            )
            return {
                'symbol': ticker['symbol'],
                'price': float(ticker['lastPrice']),
                'volume': float(ticker['volume']),
                'quote_volume': float(ticker['quoteVolume']),
                'price_change_percent': float(ticker['priceChangePercent']),
                'high': float(ticker['highPrice']),
                'low': float(ticker['lowPrice'])
            }
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error fetching ticker for {symbol}: {e}")
            raise
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error fetching ticker for {symbol}: {e}")
            raise
        except (KeyError, ValueError) as e:
            self.logger.error(f"Data parsing error for ticker {symbol}: {e}")
            raise ValueError(f"Invalid ticker data format: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error fetching ticker for {symbol}: {e}", exc_info=True)
            raise
    
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> Order:
        """
        Create a new order.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY/SELL)
            order_type: Order type (MARKET/LIMIT/STOP_LOSS/TAKE_PROFIT)
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            stop_price: Stop price (for STOP_LOSS orders)
        
        Returns:
            Order object
        """
        try:
            order_params = {
                'symbol': symbol,
                'side': side.value,
                'type': order_type.value,
                'quantity': quantity
            }
            
            if order_type == OrderType.LIMIT:
                order_params['timeInForce'] = 'GTC'
                order_params['price'] = price
            elif order_type == OrderType.STOP_LOSS:
                order_params['stopPrice'] = stop_price
                order_params['type'] = 'STOP_LOSS_LIMIT'
                order_params['price'] = price
                order_params['timeInForce'] = 'GTC'
            
            # Execute with rate limiting
            result = await self._rate_limited_request(
                self.client.create_order(**order_params)
            )
            
            return Order(
                order_id=None,
                binance_order_id=int(result['orderId']),
                symbol=symbol,
                side=OrderSide(result['side']),
                order_type=order_type,
                quantity=float(result['origQty']),
                price=float(result.get('price', 0)) if result.get('price') else None,
                status=OrderStatus(result['status']),
                filled_quantity=float(result.get('executedQty', 0)),
                filled_price=None,
                commission=0.0,
                commission_asset='',
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        except BinanceOrderException as e:
            self.logger.error(f"Binance order error: {e.code} - {e.message}")
            raise
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error creating order: {e}")
            raise
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error creating order: {e}")
            raise
        except (KeyError, ValueError) as e:
            self.logger.error(f"Data parsing error for order response: {e}")
            raise ValueError(f"Invalid order response format: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error creating order: {e}", exc_info=True)
            raise
    
    async def get_order(self, symbol: str, order_id: int) -> Optional[Order]:
        """Get order status."""
        try:
            # Execute with rate limiting
            result = await self._rate_limited_request(
                self.client.get_order(symbol=symbol, orderId=order_id)
            )
            
            return Order(
                order_id=None,
                binance_order_id=int(result['orderId']),
                symbol=symbol,
                side=OrderSide(result['side']),
                order_type=OrderType(result['type']),
                quantity=float(result['origQty']),
                price=float(result.get('price', 0)) if result.get('price') else None,
                status=OrderStatus(result['status']),
                filled_quantity=float(result.get('executedQty', 0)),
                filled_price=float(result.get('price', 0)) if result.get('price') else None,
                commission=0.0,  # Will be updated from trade history
                commission_asset='',
                created_at=datetime.fromtimestamp(result['time'] / 1000),
                updated_at=datetime.fromtimestamp(result['updateTime'] / 1000)
            )
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error fetching order {order_id}: {e}")
            return None
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error fetching order {order_id}: {e}")
            return None
        except (KeyError, ValueError) as e:
            self.logger.error(f"Data parsing error for order {order_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching order {order_id}: {e}", exc_info=True)
            return None
    
    async def cancel_order(self, symbol: str, order_id: int) -> bool:
        """Cancel an order."""
        try:
            # Execute with rate limiting
            await self._rate_limited_request(
                self.client.cancel_order(symbol=symbol, orderId=order_id)
            )
            return True
        except BinanceOrderException as e:
            # Order might already be filled or cancelled
            self.logger.warning(f"Order {order_id} cancellation failed: {e.code} - {e.message}")
            return False
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error cancelling order {order_id}: {e}")
            return False
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error cancelling order {order_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error cancelling order {order_id}: {e}", exc_info=True)
            return False
    
    async def get_account_balance(self, asset: str = "USDT") -> float:
        """Get account balance for an asset."""
        try:
            # Execute with rate limiting
            account = await self._rate_limited_request(
                self.client.get_account()
            )
            for balance in account.get('balances', []):
                if balance.get('asset') == asset:
                    return float(balance.get('free', 0))
            return 0.0
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error fetching balance: {e}")
            return 0.0
        except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
            self.logger.error(f"Network error fetching balance: {e}")
            return 0.0
        except (KeyError, ValueError) as e:
            self.logger.error(f"Data parsing error for balance: {e}")
            return 0.0
        except Exception as e:
            self.logger.error(f"Unexpected error fetching balance: {e}", exc_info=True)
            return 0.0
    
    async def subscribe_kline_stream(
        self,
        symbol: str,
        interval: str,
        callback: Callable
    ):
        """
        Subscribe to kline WebSocket stream.
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval
            callback: Callback function to handle kline updates
        """
        try:
            async def handle_socket_message(msg):
                if 'k' in msg:
                    kline_data = msg['k']
                    if kline_data['x']:  # Kline is closed
                        kline = Kline(
                            symbol=kline_data['s'],
                            open_time=datetime.fromtimestamp(kline_data['t'] / 1000),
                            close_time=datetime.fromtimestamp(kline_data['T'] / 1000),
                            open_price=float(kline_data['o']),
                            high_price=float(kline_data['h']),
                            low_price=float(kline_data['l']),
                            close_price=float(kline_data['c']),
                            volume=float(kline_data['v']),
                            quote_volume=float(kline_data['q']),
                            trades=int(kline_data['n']),
                            taker_buy_base_volume=float(kline_data['V']),
                            taker_buy_quote_volume=float(kline_data['Q'])
                        )
                        await callback(kline)
            
            stream = self.socket_manager.kline_socket(symbol, interval=interval)
            self._ws_connections[f"{symbol}_{interval}"] = stream
            
            async with stream as kline_socket:
                async for msg in kline_socket:
                    await handle_socket_message(msg)
        except (ConnectionError, asyncio.CancelledError) as e:
            self.logger.info(f"Kline stream for {symbol} closed: {e}")
        except (BinanceAPIException, BinanceRequestException) as e:
            self.logger.error(f"Binance API error in kline stream for {symbol}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error in kline stream for {symbol}: {e}", exc_info=True)
