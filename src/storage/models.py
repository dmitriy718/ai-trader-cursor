"""Database models for the trading bot."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class TradeStatus(str, Enum):
    """Trade status enumeration."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"


@dataclass
class Kline:
    """Candlestick data model."""
    symbol: str
    open_time: datetime
    close_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    quote_volume: float
    trades: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float


@dataclass
class Order:
    """Order data model."""
    order_id: Optional[int]
    binance_order_id: Optional[int]
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float]
    status: OrderStatus
    filled_quantity: float
    filled_price: Optional[float]
    commission: float
    commission_asset: str
    created_at: datetime
    updated_at: datetime
    strategy: Optional[str] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None


@dataclass
class Trade:
    """Trade data model."""
    trade_id: Optional[int]
    symbol: str
    entry_order_id: int
    exit_order_id: Optional[int]
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    side: OrderSide
    status: TradeStatus
    pnl: float
    pnl_percent: float
    fees: float
    strategy: str
    entry_time: datetime
    exit_time: Optional[datetime]
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None


@dataclass
class ScannerSignal:
    """Scanner signal data model."""
    signal_id: Optional[int]
    symbol: str
    strategy: str
    signal_type: str  # BUY, SELL
    confidence: float
    price: float
    indicators: dict
    created_at: datetime
    processed: bool = False
