"""Paper trading mode for simulated trading."""

from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal, ROUND_DOWN

from ..core.logger import setup_logger
from ..storage.models import Order, Trade, OrderSide, OrderStatus, OrderType, TradeStatus
from ..storage.database import Database


class PaperTradingEngine:
    """Paper trading engine for simulated trading without real capital."""
    
    def __init__(
        self,
        database: Database,
        initial_balance: float = 10000.0,
        commission_rate: float = 0.001
    ):
        """
        Initialize paper trading engine.
        
        Args:
            database: Database instance
            initial_balance: Initial paper trading balance in USD
            commission_rate: Commission rate (0.001 = 0.1%)
        """
        self.database = database
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.logger = setup_logger("PaperTradingEngine")
        self._balance_cache: Dict[str, float] = {'USDT': initial_balance}
    
    async def get_balance(self, asset: str = "USDT") -> float:
        """Get paper trading balance for an asset."""
        return self._balance_cache.get(asset, 0.0)
    
    async def execute_paper_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None
    ) -> Order:
        """
        Execute a paper trade order.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY/SELL)
            order_type: Order type
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
        
        Returns:
            Order object with filled status
        """
        try:
            # For paper trading, market orders execute at current price
            # In real implementation, would fetch current price from exchange
            execution_price = price if price else self._get_mock_price(symbol)
            
            # Calculate costs
            base_asset = symbol.replace("USDT", "")
            cost_usdt = quantity * execution_price
            
            if side == OrderSide.BUY:
                # Check balance
                if self._balance_cache.get("USDT", 0) < cost_usdt * (1 + self.commission_rate):
                    raise ValueError("Insufficient balance for paper trade")
                
                # Execute buy
                commission = cost_usdt * self.commission_rate
                self._balance_cache["USDT"] -= (cost_usdt + commission)
                self._balance_cache[base_asset] = self._balance_cache.get(base_asset, 0) + quantity
            
            else:  # SELL
                # Check balance
                if self._balance_cache.get(base_asset, 0) < quantity:
                    raise ValueError("Insufficient balance for paper trade")
                
                # Execute sell
                revenue_usdt = quantity * execution_price
                commission = revenue_usdt * self.commission_rate
                self._balance_cache[base_asset] -= quantity
                self._balance_cache["USDT"] += (revenue_usdt - commission)
            
            # Create order record
            order = Order(
                order_id=None,
                binance_order_id=None,  # Paper trades don't have exchange order IDs
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=execution_price,
                status=OrderStatus.FILLED,
                filled_quantity=quantity,
                filled_price=execution_price,
                commission=commission,
                commission_asset="USDT",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Store in database
            order_id = await self.database.insert_order(order)
            order.order_id = order_id
            
            self.logger.info(
                f"Paper trade executed: {side.value} {quantity:.8f} {symbol} @ ${execution_price:.8f}"
            )
            
            return order
        
        except Exception as e:
            self.logger.error(f"Error executing paper order: {e}")
            raise
    
    def _get_mock_price(self, symbol: str) -> float:
        """Get mock price for paper trading (would fetch from exchange in real implementation)."""
        # Mock prices - in real implementation, fetch from exchange
        mock_prices = {
            "BTCUSDT": 45000.0,
            "ETHUSDT": 3000.0,
            "SOLUSDT": 100.0,
            "BNBUSDT": 300.0,
        }
        return mock_prices.get(symbol, 1.0)
    
    async def get_portfolio_value(self) -> Dict[str, Any]:
        """Get current portfolio value."""
        total_usdt = self._balance_cache.get("USDT", 0)
        
        # Calculate value of other assets (would fetch real prices)
        for asset, quantity in self._balance_cache.items():
            if asset != "USDT" and quantity > 0:
                symbol = f"{asset}USDT"
                price = self._get_mock_price(symbol)
                total_usdt += quantity * price
        
        return {
            'total_value_usdt': total_usdt,
            'initial_balance': self.initial_balance,
            'pnl': total_usdt - self.initial_balance,
            'pnl_percent': ((total_usdt - self.initial_balance) / self.initial_balance) * 100,
            'balances': self._balance_cache.copy()
        }
