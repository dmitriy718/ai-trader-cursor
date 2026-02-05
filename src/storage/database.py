"""Database operations using SQLite with WAL mode."""

import asyncio
import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from .models import (
    Kline, Order, Trade, ScannerSignal,
    OrderSide, OrderStatus, OrderType, TradeStatus
)


class Database:
    """SQLite database manager with WAL mode and connection pool for high concurrency."""
    
    def __init__(self, db_path: str, wal_mode: bool = True, pool_size: Optional[int] = None):
        """
        Initialize database connection pool.
        
        Args:
            db_path: Path to SQLite database file
            wal_mode: Enable Write-Ahead Logging mode
            pool_size: Maximum number of connections in pool (default from constants)
        """
        from ..core.constants import DEFAULT_POOL_SIZE
        
        self.db_path = db_path
        self.wal_mode = wal_mode
        self.pool_size = pool_size if pool_size is not None else DEFAULT_POOL_SIZE
        self._pool: Optional[aiosqlite.Connection] = None
        self._connection_semaphore: Optional[asyncio.Semaphore] = None
        self._initialized = False
        
        # Ensure database directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """Initialize database connection pool and create tables."""
        if self._initialized:
            return
        
        # Create main connection for schema operations
        self._pool = await aiosqlite.connect(
            self.db_path,
            timeout=30.0  # 30 second timeout for connection
        )
        
        # Configure connection for performance
        if self.wal_mode:
            await self._pool.execute("PRAGMA journal_mode=WAL")
            await self._pool.execute("PRAGMA synchronous=NORMAL")
            await self._pool.execute("PRAGMA cache_size=10000")
            await self._pool.execute("PRAGMA temp_store=MEMORY")
            await self._pool.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        
        # Create tables
        await self._create_tables()
        await self._pool.commit()
        
        # Create semaphore to limit concurrent connections
        # SQLite with WAL mode can handle multiple readers, but we limit writers
        self._connection_semaphore = asyncio.Semaphore(self.pool_size)
        self._initialized = True
    
    async def close(self):
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        self._initialized = False
    
    @asynccontextmanager
    async def get_connection(self):
        """
        Get database connection from pool with semaphore-based concurrency control.
        
        For SQLite with WAL mode, multiple readers can work concurrently,
        but we use a semaphore to prevent connection exhaustion.
        """
        if not self._initialized:
            await self.initialize()
        
        # Acquire semaphore to limit concurrent operations
        async with self._connection_semaphore:
            # For SQLite with WAL, we can use the main connection for reads
            # For writes, we ensure proper transaction handling
            yield self._pool
    
    @asynccontextmanager
    async def transaction(self):
        """
        Context manager for database transactions.
        
        Ensures all operations within the context are atomic.
        Rolls back on exception, commits on success.
        
        Example:
            async with db.transaction():
                await db.insert_order(order)
                await db.insert_trade(trade)
        """
        if not self._initialized:
            await self.initialize()
        
        async with self._connection_semaphore:
            try:
                # Begin transaction
                await self._pool.execute("BEGIN TRANSACTION")
                yield self._pool
                # Commit on success
                await self._pool.commit()
            except Exception as e:
                # Rollback on error
                await self._pool.rollback()
                raise
    
    async def _create_tables(self):
        """Create database tables."""
        # Klines table
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                close_time INTEGER NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL NOT NULL,
                trades INTEGER NOT NULL,
                taker_buy_base_volume REAL NOT NULL,
                taker_buy_quote_volume REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, open_time)
            )
        """)
        
        # Orders table
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                binance_order_id INTEGER,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL,
                status TEXT NOT NULL,
                filled_quantity REAL DEFAULT 0,
                filled_price REAL,
                commission REAL DEFAULT 0,
                commission_asset TEXT,
                strategy TEXT,
                stop_loss_price REAL,
                take_profit_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Trades table
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_order_id INTEGER NOT NULL,
                exit_order_id INTEGER,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity REAL NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                pnl REAL DEFAULT 0,
                pnl_percent REAL DEFAULT 0,
                fees REAL DEFAULT 0,
                strategy TEXT NOT NULL,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP,
                stop_loss_price REAL,
                take_profit_price REAL,
                trailing_stop_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Scanner signals table
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS scanner_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                price REAL NOT NULL,
                indicators TEXT NOT NULL,
                processed BOOLEAN DEFAULT 0,
                processing BOOLEAN DEFAULT 0,
                error_message TEXT,
                processed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for performance
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_klines_symbol_time 
            ON klines(symbol, open_time DESC)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_symbol_status 
            ON orders(symbol, status)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_symbol_status 
            ON trades(symbol, status)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_symbol_processed 
            ON scanner_signals(symbol, processed, processing)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_created_at 
            ON scanner_signals(created_at DESC)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_entry_time 
            ON trades(entry_time DESC)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_created_at 
            ON orders(created_at DESC)
        """)
        await self._pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_klines_open_time 
            ON klines(open_time DESC)
        """)
    
    # Kline operations
    async def insert_klines(self, klines: List[Kline]):
        """
        Insert klines into database using batch insert for efficiency.
        
        Args:
            klines: List of Kline objects to insert
        """
        from ..core.constants import BATCH_INSERT_CHUNK_SIZE
        
        if not klines:
            return
        
        async with self.get_connection() as conn:
            # Batch insert in chunks to avoid memory issues
            chunk_size = BATCH_INSERT_CHUNK_SIZE
            for i in range(0, len(klines), chunk_size):
                chunk = klines[i:i + chunk_size]
                await conn.executemany("""
                    INSERT OR REPLACE INTO klines 
                    (symbol, open_time, close_time, open_price, high_price, low_price,
                     close_price, volume, quote_volume, trades, taker_buy_base_volume,
                     taker_buy_quote_volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (
                        k.symbol,
                        int(k.open_time.timestamp() * 1000),
                        int(k.close_time.timestamp() * 1000),
                        k.open_price, k.high_price, k.low_price, k.close_price,
                        k.volume, k.quote_volume, k.trades,
                        k.taker_buy_base_volume, k.taker_buy_quote_volume
                    )
                    for k in chunk
                ])
            await conn.commit()
    
    async def get_klines(
        self,
        symbol: str,
        limit: int = 200,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """
        Get klines for a symbol with optimized query.
        
        Uses index hint for better performance on large datasets.
        """
        async with self.get_connection() as conn:
            # Use index hint for better query performance
            query = """
                SELECT symbol, open_time, close_time, open_price, high_price,
                       low_price, close_price, volume, quote_volume, trades,
                       taker_buy_base_volume, taker_buy_quote_volume
                FROM klines
                WHERE symbol = ?
            """
            params = [symbol]
            
            if end_time:
                query += " AND open_time <= ?"
                params.append(int(end_time.timestamp() * 1000))
            
            # ORDER BY uses idx_klines_symbol_time index
            query += " ORDER BY open_time DESC LIMIT ?"
            params.append(limit)
            
            rows = await conn.execute_fetchall(query, params)
            
            return [
                Kline(
                    symbol=row[0],
                    open_time=datetime.fromtimestamp(row[1] / 1000),
                    close_time=datetime.fromtimestamp(row[2] / 1000),
                    open_price=row[3],
                    high_price=row[4],
                    low_price=row[5],
                    close_price=row[6],
                    volume=row[7],
                    quote_volume=row[8],
                    trades=row[9],
                    taker_buy_base_volume=row[10],
                    taker_buy_quote_volume=row[11]
                )
                for row in rows
            ][::-1]  # Reverse to get chronological order
    
    # Order operations
    async def insert_order(self, order: Order) -> int:
        """Insert order and return order ID."""
        async with self.get_connection() as conn:
            cursor = await conn.execute("""
                INSERT INTO orders 
                (binance_order_id, symbol, side, order_type, quantity, price,
                 status, filled_quantity, filled_price, commission, commission_asset,
                 strategy, stop_loss_price, take_profit_price, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.binance_order_id,
                order.symbol,
                order.side.value,
                order.order_type.value,
                order.quantity,
                order.price,
                order.status.value,
                order.filled_quantity,
                order.filled_price,
                order.commission,
                order.commission_asset,
                order.strategy,
                order.stop_loss_price,
                order.take_profit_price,
                order.created_at,
                order.updated_at
            ))
            await conn.commit()
            return cursor.lastrowid
    
    async def update_order(self, order: Order):
        """Update order in database."""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE orders SET
                    status = ?,
                    filled_quantity = ?,
                    filled_price = ?,
                    commission = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                order.status.value,
                order.filled_quantity,
                order.filled_price,
                order.commission,
                datetime.now(),
                order.order_id
            ))
            await conn.commit()
    
    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Order]:
        """
        Get open orders with optional filtering and pagination.
        
        Args:
            symbol: Optional symbol filter
            limit: Optional limit on number of results
        
        Returns:
            List of open orders
        """
        async with self.get_connection() as conn:
            query = """
                SELECT id, binance_order_id, symbol, side, order_type, quantity,
                       price, status, filled_quantity, filled_price, commission,
                       commission_asset, strategy, stop_loss_price, take_profit_price,
                       created_at, updated_at
                FROM orders
                WHERE status IN ('PENDING', 'PARTIALLY_FILLED')
            """
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            # Add ordering for consistent results
            query += " ORDER BY created_at DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            rows = await conn.execute_fetchall(query, params)
            
            return [
                Order(
                    order_id=row[0],
                    binance_order_id=row[1],
                    symbol=row[2],
                    side=OrderSide(row[3]),
                    order_type=OrderType(row[4]),
                    quantity=row[5],
                    price=row[6],
                    status=OrderStatus(row[7]),
                    filled_quantity=row[8],
                    filled_price=row[9],
                    commission=row[10],
                    commission_asset=row[11],
                    strategy=row[12],
                    stop_loss_price=row[13],
                    take_profit_price=row[14],
                    created_at=datetime.fromisoformat(row[15]),
                    updated_at=datetime.fromisoformat(row[16])
                )
                for row in rows
            ]
    
    # Trade operations
    async def insert_trade(self, trade: Trade) -> int:
        """Insert trade and return trade ID."""
        async with self.get_connection() as conn:
            cursor = await conn.execute("""
                INSERT INTO trades 
                (symbol, entry_order_id, exit_order_id, entry_price, exit_price,
                 quantity, side, status, pnl, pnl_percent, fees, strategy,
                 entry_time, exit_time, stop_loss_price, take_profit_price,
                 trailing_stop_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.symbol,
                trade.entry_order_id,
                trade.exit_order_id,
                trade.entry_price,
                trade.exit_price,
                trade.quantity,
                trade.side.value,
                trade.status.value,
                trade.pnl,
                trade.pnl_percent,
                trade.fees,
                trade.strategy,
                trade.entry_time,
                trade.exit_time,
                trade.stop_loss_price,
                trade.take_profit_price,
                trade.trailing_stop_price
            ))
            await conn.commit()
            return cursor.lastrowid
    
    async def update_trade(self, trade: Trade):
        """Update trade in database."""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE trades SET
                    exit_order_id = ?,
                    exit_price = ?,
                    status = ?,
                    pnl = ?,
                    pnl_percent = ?,
                    fees = ?,
                    exit_time = ?,
                    trailing_stop_price = ?
                WHERE id = ?
            """, (
                trade.exit_order_id,
                trade.exit_price,
                trade.status.value,
                trade.pnl,
                trade.pnl_percent,
                trade.fees,
                trade.exit_time,
                trade.trailing_stop_price,
                trade.trade_id
            ))
            await conn.commit()
    
    async def get_open_trades(
        self,
        symbol: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Trade]:
        """
        Get open trades with optional filtering and pagination.
        
        Args:
            symbol: Optional symbol filter
            limit: Optional limit on number of results
        
        Returns:
            List of open trades
        """
        async with self.get_connection() as conn:
            query = """
                SELECT id, symbol, entry_order_id, exit_order_id, entry_price,
                       exit_price, quantity, side, status, pnl, pnl_percent, fees,
                       strategy, entry_time, exit_time, stop_loss_price,
                       take_profit_price, trailing_stop_price
                FROM trades
                WHERE status = 'OPEN'
            """
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            # Add index hint for better performance
            query += " ORDER BY entry_time DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            rows = await conn.execute_fetchall(query, params)
            
            return [
                Trade(
                    trade_id=row[0],
                    symbol=row[1],
                    entry_order_id=row[2],
                    exit_order_id=row[3],
                    entry_price=row[4],
                    exit_price=row[5],
                    quantity=row[6],
                    side=OrderSide(row[7]),
                    status=TradeStatus(row[8]),
                    pnl=row[9],
                    pnl_percent=row[10],
                    fees=row[11],
                    strategy=row[12],
                    entry_time=datetime.fromisoformat(row[13]),
                    exit_time=datetime.fromisoformat(row[14]) if row[14] else None,
                    stop_loss_price=row[15],
                    take_profit_price=row[16],
                    trailing_stop_price=row[17]
                )
                for row in rows
            ]
    
    async def get_daily_pnl(self, date: Optional[datetime] = None) -> float:
        """Get daily PnL."""
        async with self.get_connection() as conn:
            if date:
                query = """
                    SELECT COALESCE(SUM(pnl), 0)
                    FROM trades
                    WHERE DATE(exit_time) = DATE(?)
                    AND status = 'CLOSED'
                """
                params = [date]
            else:
                query = """
                    SELECT COALESCE(SUM(pnl), 0)
                    FROM trades
                    WHERE DATE(exit_time) = DATE('now')
                    AND status = 'CLOSED'
                """
                params = []
            
            row = await conn.execute_fetchone(query, params)
            return row[0] if row else 0.0
    
    # Scanner signal operations
    async def insert_signal(self, signal: ScannerSignal) -> int:
        """Insert scanner signal and return signal ID."""
        async with self.get_connection() as conn:
            cursor = await conn.execute("""
                INSERT INTO scanner_signals 
                (symbol, strategy, signal_type, confidence, price, indicators, processed, processing)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                signal.symbol,
                signal.strategy,
                signal.signal_type,
                signal.confidence,
                signal.price,
                json.dumps(signal.indicators),
                signal.processed
            ))
            await conn.commit()
            return cursor.lastrowid
    
    async def get_unprocessed_signals(
        self,
        limit: Optional[int] = None,
        symbol: Optional[str] = None
    ) -> List[ScannerSignal]:
        """
        Get unprocessed scanner signals with optional filtering.
        
        Args:
            limit: Maximum number of signals to return (default from constants)
            symbol: Optional symbol filter
        
        Returns:
            List of unprocessed signals
        """
        from ..core.constants import DEFAULT_QUERY_LIMIT
        
        if limit is None:
            limit = DEFAULT_QUERY_LIMIT
        
        async with self.get_connection() as conn:
            query = """
                SELECT id, symbol, strategy, signal_type, confidence, price,
                       indicators, processed, processing, created_at
                FROM scanner_signals
                WHERE processed = 0 AND processing = 0
            """
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = await conn.execute_fetchall(query, params)
            
            return [
                ScannerSignal(
                    signal_id=row[0],
                    symbol=row[1],
                    strategy=row[2],
                    signal_type=row[3],
                    confidence=row[4],
                    price=row[5],
                    indicators=json.loads(row[6]),
                    processed=bool(row[7]),
                    created_at=datetime.fromisoformat(row[9])
                )
                for row in rows
            ]
    
    async def mark_signal_processing(self, signal_id: int) -> bool:
        """
        Mark signal as processing (atomic operation to prevent race conditions).
        
        Returns:
            True if successfully marked as processing, False if already processing/processed
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute("""
                UPDATE scanner_signals 
                SET processing = 1 
                WHERE id = ? AND processed = 0 AND processing = 0
            """, (signal_id,))
            await conn.commit()
            return cursor.rowcount > 0
    
    async def mark_signal_processed(self, signal_id: int):
        """Mark signal as processed."""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE scanner_signals 
                SET processed = 1, processing = 0, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (signal_id,))
            await conn.commit()
    
    async def mark_signal_failed(self, signal_id: int, error_message: str):
        """Mark signal as failed with error message."""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE scanner_signals 
                SET processing = 0, error_message = ?
                WHERE id = ?
            """, (error_message[:500], signal_id))  # Limit error message length
            await conn.commit()
    
    async def reset_stuck_signals(self, timeout_minutes: int = 30):
        """Reset signals stuck in processing state (in case of crash)."""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE scanner_signals 
                SET processing = 0
                WHERE processing = 1 
                AND processed = 0
                AND created_at < datetime('now', '-' || ? || ' minutes')
            """, (timeout_minutes,))
            await conn.commit()
