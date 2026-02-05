"""Advanced risk management system."""

import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from collections import defaultdict

from ..core.logger import setup_logger
from ..storage.models import Trade, OrderSide, Kline
from ..indicators.technical import TechnicalIndicators


class RiskManager:
    """Advanced risk management with multiple safety checks."""
    
    def __init__(
        self,
        risk_per_trade: float = 0.02,
        max_position_size_usd: float = 1000.0,
        daily_loss_limit_usd: float = 100.0,
        trade_cooldown_seconds: int = 300,
        adx_chop_threshold: float = 25.0,
        atr_multiplier: float = 2.0,
        max_spread_percent: float = 0.5,
        min_book_liquidity_usd: float = 5000.0,
        order_book_imbalance_threshold: float = 0.3
    ):
        """
        Initialize risk manager.
        
        Args:
            risk_per_trade: Percentage of capital to risk per trade (0.02 = 2%)
            max_position_size_usd: Maximum position size in USD
            daily_loss_limit_usd: Daily loss limit in USD
            trade_cooldown_seconds: Cooldown between trades on same symbol
            adx_chop_threshold: ADX threshold for chop detection
            atr_multiplier: ATR multiplier for stop loss
            max_spread_percent: Maximum bid/ask spread percentage
            min_book_liquidity_usd: Minimum order book liquidity in USD
            order_book_imbalance_threshold: Maximum order book imbalance
        """
        self.risk_per_trade = risk_per_trade
        self.max_position_size_usd = max_position_size_usd
        self.daily_loss_limit_usd = daily_loss_limit_usd
        self.trade_cooldown_seconds = trade_cooldown_seconds
        self.adx_chop_threshold = adx_chop_threshold
        self.atr_multiplier = atr_multiplier
        self.max_spread_percent = max_spread_percent
        self.min_book_liquidity_usd = min_book_liquidity_usd
        self.order_book_imbalance_threshold = order_book_imbalance_threshold
        
        self.logger = setup_logger("RiskManager")
        self.last_trade_time: Dict[str, datetime] = {}
        self.daily_pnl: float = 0.0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    def reset_daily_stats(self):
        """Reset daily statistics at midnight."""
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.daily_pnl = 0.0
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self.logger.info("Daily statistics reset")
    
    def update_daily_pnl(self, pnl: float):
        """Update daily PnL."""
        self.reset_daily_stats()
        self.daily_pnl += pnl
    
    def check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit has been reached."""
        self.reset_daily_stats()
        if self.daily_pnl <= -self.daily_loss_limit_usd:
            self.logger.warning(f"Daily loss limit reached: ${self.daily_pnl:.2f}")
            return False
        return True
    
    def check_trade_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period."""
        if symbol not in self.last_trade_time:
            return True
        
        last_trade = self.last_trade_time[symbol]
        elapsed = (datetime.now() - last_trade).total_seconds()
        
        if elapsed < self.trade_cooldown_seconds:
            self.logger.debug(
                f"Symbol {symbol} in cooldown: {self.trade_cooldown_seconds - elapsed:.0f}s remaining"
            )
            return False
        
        return True
    
    def record_trade(self, symbol: str):
        """Record a trade for cooldown tracking."""
        self.last_trade_time[symbol] = datetime.now()
    
    def detect_chop(self, klines: list[Kline]) -> bool:
        """
        Detect choppy/sideways market using ADX.
        
        Returns:
            True if market is choppy (should avoid trading)
        """
        if len(klines) < 28:  # Need at least 14 periods for ADX
            return True  # Assume chop if not enough data
        
        df = TechnicalIndicators.klines_to_dataframe(klines)
        adx_data = TechnicalIndicators.calculate_adx(df)
        
        if len(adx_data['adx']) == 0:
            return True
        
        current_adx = adx_data['adx'].iloc[-1]
        
        if pd.isna(current_adx):
            return True
        
        # Market is choppy if ADX is below threshold
        is_chop = current_adx < self.adx_chop_threshold
        
        if is_chop:
            self.logger.debug(f"Chop detected: ADX={current_adx:.2f} < {self.adx_chop_threshold}")
        
        return is_chop
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        side: OrderSide,
        klines: list[Kline]
    ) -> float:
        """
        Calculate stop loss price using ATR.
        
        Args:
            entry_price: Entry price
            side: Trade side (BUY/SELL)
            klines: Historical klines for ATR calculation
        
        Returns:
            Stop loss price
        """
        if len(klines) < 14:
            # Fallback: use 2% stop loss
            if side == OrderSide.BUY:
                return entry_price * 0.98
            else:
                return entry_price * 1.02
        
        df = TechnicalIndicators.klines_to_dataframe(klines)
        atr = TechnicalIndicators.calculate_atr(df)
        
        if len(atr) == 0 or pd.isna(atr.iloc[-1]):
            # Fallback
            if side == OrderSide.BUY:
                return entry_price * 0.98
            else:
                return entry_price * 1.02
        
        current_atr = atr.iloc[-1]
        stop_distance = current_atr * self.atr_multiplier
        
        if side == OrderSide.BUY:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        account_balance: float
    ) -> float:
        """
        Calculate position size based on risk per trade.
        
        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            account_balance: Account balance in USD
        
        Returns:
            Position size in base asset
        
        Raises:
            ValueError: If inputs are invalid
        """
        # Validate inputs
        if account_balance <= 0:
            raise ValueError(f"Account balance must be greater than zero, got {account_balance}")
        
        if entry_price <= 0:
            raise ValueError(f"Entry price must be greater than zero, got {entry_price}")
        
        if stop_loss_price <= 0:
            raise ValueError(f"Stop loss price must be greater than zero, got {stop_loss_price}")
        
        if self.risk_per_trade <= 0 or self.risk_per_trade > 1:
            raise ValueError(
                f"Risk per trade must be between 0 and 1 (exclusive), got {self.risk_per_trade}"
            )
        
        risk_amount = account_balance * self.risk_per_trade
        price_risk = abs(entry_price - stop_loss_price)
        
        if price_risk == 0:
            self.logger.warning(
                f"Price risk is zero (entry={entry_price}, stop_loss={stop_loss_price}). "
                f"Returning zero position size."
            )
            return 0.0
        
        position_size = risk_amount / price_risk
        
        # Cap position size
        max_position = self.max_position_size_usd / entry_price
        position_size = min(position_size, max_position)
        
        return position_size
    
    def check_liquidity(self, order_book: Dict[str, Any]) -> tuple[bool, str]:
        """
        Check order book liquidity and spread.
        
        Args:
            order_book: Order book data from Binance
        
        Returns:
            Tuple of (is_valid, reason)
        """
        spread_percent = order_book.get('spread_percent', 0)
        min_liquidity = order_book.get('min_liquidity_usd', 0)
        imbalance = abs(order_book.get('imbalance', 0))
        
        if spread_percent > self.max_spread_percent:
            return False, f"Spread too wide: {spread_percent:.2f}%"
        
        if min_liquidity < self.min_book_liquidity_usd:
            return False, f"Insufficient liquidity: ${min_liquidity:.2f}"
        
        if imbalance > self.order_book_imbalance_threshold:
            return False, f"Order book imbalance: {imbalance:.2f}"
        
        return True, "OK"
    
    def calculate_breakeven_price(
        self,
        entry_price: float,
        quantity: float,
        fees_percent: Optional[float] = None
    ) -> float:
        """
        Calculate breakeven price including fees.
        
        Args:
            entry_price: Entry price
            quantity: Position quantity
            fees_percent: Trading fees percentage (default from constants)
        
        Returns:
            Breakeven price
        
        Raises:
            ValueError: If quantity is zero or negative, or fees_percent is invalid
        """
        from ..core.constants import DEFAULT_FEES_PERCENT
        
        # Use default if not provided
        if fees_percent is None:
            fees_percent = DEFAULT_FEES_PERCENT
        
        # Validate inputs
        if quantity <= 0:
            raise ValueError(f"Quantity must be greater than zero, got {quantity}")
        
        if entry_price <= 0:
            raise ValueError(f"Entry price must be greater than zero, got {entry_price}")
        
        if fees_percent < 0 or fees_percent >= 1:
            raise ValueError(
                f"Fees percent must be between 0 and 1 (exclusive), got {fees_percent}"
            )
        
        # Entry fees
        entry_cost = entry_price * quantity * (1 + fees_percent)
        
        # Breakeven price (including exit fees)
        # Denominator: quantity * (1 - fees_percent)
        # Since quantity > 0 and fees_percent < 1, denominator is always positive
        denominator = quantity * (1 - fees_percent)
        
        if denominator <= 0:
            # This should never happen with valid inputs, but add safety check
            raise ValueError(
                f"Invalid calculation: denominator is {denominator}. "
                f"Quantity: {quantity}, Fees: {fees_percent}"
            )
        
        breakeven = entry_cost / denominator
        
        return breakeven
    
    def should_move_to_breakeven(
        self,
        trade: Trade,
        current_price: float,
        breakeven_trigger_percent: float = 0.5
    ) -> bool:
        """
        Check if stop loss should be moved to breakeven.
        
        Args:
            trade: Open trade
            current_price: Current market price
            breakeven_trigger_percent: Profit percentage to trigger breakeven move
        
        Returns:
            True if stop loss should be moved to breakeven
        """
        if trade.side == OrderSide.BUY:
            profit_percent = ((current_price - trade.entry_price) / trade.entry_price) * 100
        else:
            profit_percent = ((trade.entry_price - current_price) / trade.entry_price) * 100
        
        if profit_percent >= breakeven_trigger_percent:
            # Check if stop loss is not already at breakeven
            breakeven_price = self.calculate_breakeven_price(
                trade.entry_price,
                trade.quantity
            )
            
            if trade.side == OrderSide.BUY:
                if trade.stop_loss_price is None or trade.stop_loss_price < breakeven_price:
                    return True
            else:
                if trade.stop_loss_price is None or trade.stop_loss_price > breakeven_price:
                    return True
        
        return False
    
    def calculate_trailing_stop(
        self,
        trade: Trade,
        current_price: float,
        klines: list[Kline]
    ) -> Optional[float]:
        """
        Calculate trailing stop loss price.
        
        Args:
            trade: Open trade
            current_price: Current market price
            klines: Historical klines for ATR calculation
        
        Returns:
            New trailing stop price or None
        """
        if len(klines) < 14:
            return None
        
        df = TechnicalIndicators.klines_to_dataframe(klines)
        atr = TechnicalIndicators.calculate_atr(df)
        
        if len(atr) == 0 or pd.isna(atr.iloc[-1]):
            return None
        
        current_atr = atr.iloc[-1]
        trail_distance = current_atr * self.atr_multiplier
        
        if trade.side == OrderSide.BUY:
            new_stop = current_price - trail_distance
            # Only move stop loss up
            if trade.trailing_stop_price is None or new_stop > trade.trailing_stop_price:
                return new_stop
        else:
            new_stop = current_price + trail_distance
            # Only move stop loss down
            if trade.trailing_stop_price is None or new_stop < trade.trailing_stop_price:
                return new_stop
        
        return None
    
    def validate_trade(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        klines: list[Kline],
        order_book: Dict[str, Any],
        account_balance: float
    ) -> tuple[bool, str, Optional[float], Optional[float]]:
        """
        Comprehensive trade validation.
        
        Returns:
            Tuple of (is_valid, reason, stop_loss_price, position_size)
        """
        # Check daily loss limit
        if not self.check_daily_loss_limit():
            return False, "Daily loss limit reached", None, None
        
        # Check trade cooldown
        if not self.check_trade_cooldown(symbol):
            return False, "Symbol in cooldown period", None, None
        
        # Check for chop
        if self.detect_chop(klines):
            return False, "Choppy market detected (low ADX)", None, None
        
        # Check liquidity
        is_valid, reason = self.check_liquidity(order_book)
        if not is_valid:
            return False, reason, None, None
        
        # Calculate stop loss
        stop_loss_price = self.calculate_stop_loss(entry_price, side, klines)
        
        # Calculate position size
        position_size = self.calculate_position_size(
            entry_price,
            stop_loss_price,
            account_balance
        )
        
        if position_size == 0:
            return False, "Position size too small", None, None
        
        return True, "OK", stop_loss_price, position_size
