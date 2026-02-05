"""Trade monitoring utilities."""

from typing import List, Optional
from datetime import datetime
from ..storage.models import Trade, OrderSide, TradeStatus
from ..storage.database import Database
from ..api.binance_client import BinanceClient


class TradeMonitor:
    """Monitor open trades and manage exits."""
    
    def __init__(self, database: Database, binance_client: BinanceClient):
        """
        Initialize trade monitor.
        
        Args:
            database: Database instance
            binance_client: Binance API client
        """
        self.database = database
        self.binance_client = binance_client
    
    async def check_trade_exit_conditions(
        self,
        trade: Trade,
        current_price: float
    ) -> Optional[str]:
        """
        Check if trade should be exited.
        
        Args:
            trade: Trade to check
            current_price: Current market price
        
        Returns:
            Exit reason if trade should be closed, None otherwise
        """
        # Check stop loss
        if trade.stop_loss_price:
            if trade.side == OrderSide.BUY and current_price <= trade.stop_loss_price:
                return "stop_loss"
            elif trade.side == OrderSide.SELL and current_price >= trade.stop_loss_price:
                return "stop_loss"
        
        # Check take profit
        if trade.take_profit_price:
            if trade.side == OrderSide.BUY and current_price >= trade.take_profit_price:
                return "take_profit"
            elif trade.side == OrderSide.SELL and current_price <= trade.take_profit_price:
                return "take_profit"
        
        # Check trailing stop
        if trade.trailing_stop_price:
            if trade.side == OrderSide.BUY and current_price <= trade.trailing_stop_price:
                return "trailing_stop"
            elif trade.side == OrderSide.SELL and current_price >= trade.trailing_stop_price:
                return "trailing_stop"
        
        return None
    
    async def update_trailing_stop(
        self,
        trade: Trade,
        current_price: float,
        atr_multiplier: float = 2.0
    ) -> Optional[float]:
        """
        Update trailing stop loss based on price movement.
        
        Args:
            trade: Trade to update
            current_price: Current market price
            atr_multiplier: ATR multiplier for trailing stop
        
        Returns:
            New trailing stop price if updated, None otherwise
        """
        if trade.side == OrderSide.BUY:
            # For long positions, trail stop loss upward
            if not trade.trailing_stop_price:
                trade.trailing_stop_price = trade.entry_price * 0.98  # Initial 2% stop
            
            # Calculate new trailing stop (higher than current)
            new_trailing_stop = current_price * (1 - atr_multiplier * 0.01)
            
            if new_trailing_stop > trade.trailing_stop_price:
                return new_trailing_stop
        
        else:  # SELL
            # For short positions, trail stop loss downward
            if not trade.trailing_stop_price:
                trade.trailing_stop_price = trade.entry_price * 1.02  # Initial 2% stop
            
            # Calculate new trailing stop (lower than current)
            new_trailing_stop = current_price * (1 + atr_multiplier * 0.01)
            
            if new_trailing_stop < trade.trailing_stop_price:
                return new_trailing_stop
        
        return None
