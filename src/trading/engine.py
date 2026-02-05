"""Trading engine with unified fill processor."""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

from ..core.logger import setup_logger, get_contextual_logger
from ..core.notifications import NotificationManager
from ..storage.models import Order, Trade, OrderSide, OrderStatus, OrderType, TradeStatus
from ..storage.database import Database
from ..api.binance_client import BinanceClient
from ..risk.manager import RiskManager
from ..ml.predictor import PricePredictor
from .monitor import TradeMonitor


class UnifiedFillProcessor:
    """Unified processor for order fills and trade updates."""
    
    def __init__(self, database: Database) -> None:
        """
        Initialize fill processor.
        
        Args:
            database: Database instance
        
        Example:
            >>> processor = UnifiedFillProcessor(database)
            >>> await processor.process_order_fill(order)
        """
        self.database = database
        self.logger = setup_logger("UnifiedFillProcessor")
        self.ram_state: Dict[str, Any] = {
            'orders': {},
            'trades': {},
            'positions': {}
        }
    
    async def process_order_fill(self, order: Order) -> None:
        """
        Process order fill and update RAM state and database.
        
        Args:
            order: Filled order
        """
        try:
            # Update RAM state
            self.ram_state['orders'][order.binance_order_id] = {
                'status': order.status.value,
                'filled_quantity': order.filled_quantity,
                'filled_price': order.filled_price,
                'updated_at': datetime.now()
            }
            
            # Update database
            await self.database.update_order(order)
            
            # If order is filled, check for trade creation/update
            if order.status == OrderStatus.FILLED:
                await self._handle_filled_order(order)
        
        except Exception as e:
            self.logger.error(f"Error processing order fill: {e}")
    
    async def _handle_filled_order(self, order: Order):
        """
        Handle filled order and create/update trade using transactions.
        
        Ensures atomicity: either both order and trade are updated, or neither.
        """
        # Use transaction to ensure atomicity
        async with self.database.transaction():
            # Check if this is an entry or exit order
            open_trades = await self.database.get_open_trades(order.symbol)
            
            if order.side == OrderSide.BUY:
                # Entry order - create new trade
                trade = Trade(
                    trade_id=None,
                    symbol=order.symbol,
                    entry_order_id=order.order_id,
                    exit_order_id=None,
                    entry_price=order.filled_price or order.price or 0.0,
                    exit_price=None,
                    quantity=order.filled_quantity,
                    side=OrderSide.BUY,
                    status=TradeStatus.OPEN,
                    pnl=0.0,
                    pnl_percent=0.0,
                    fees=order.commission,
                    strategy=order.strategy or "unknown",
                    entry_time=datetime.now(),
                    exit_time=None,
                    stop_loss_price=order.stop_loss_price,
                    take_profit_price=order.take_profit_price
                )
                
                trade_id = await self.database.insert_trade(trade)
                trade.trade_id = trade_id
                
                # Update RAM state (outside transaction, but after successful insert)
                self.ram_state['trades'][trade_id] = {
                    'symbol': trade.symbol,
                    'entry_price': trade.entry_price,
                    'quantity': trade.quantity,
                    'status': trade.status.value,
                    'pnl': trade.pnl
                }
            
            elif order.side == OrderSide.SELL and open_trades:
                # Exit order - close trade
                trade = open_trades[0]  # Close first open trade
                trade.exit_order_id = order.order_id
                trade.exit_price = order.filled_price or order.price or 0.0
                trade.exit_time = datetime.now()
                trade.status = TradeStatus.CLOSED
                
                # Calculate PnL
                if trade.side == OrderSide.BUY:
                    trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
                else:
                    trade.pnl = (trade.entry_price - trade.exit_price) * trade.quantity
                
                trade.pnl_percent = (trade.pnl / (trade.entry_price * trade.quantity)) * 100
                trade.fees += order.commission
                
                await self.database.update_trade(trade)
                
                # Update RAM state (outside transaction, but after successful update)
                if trade.trade_id in self.ram_state['trades']:
                    self.ram_state['trades'][trade.trade_id]['status'] = TradeStatus.CLOSED.value
                    self.ram_state['trades'][trade.trade_id]['pnl'] = trade.pnl
    
    def get_ram_state(self) -> Dict[str, Any]:
        """Get current RAM state."""
        return self.ram_state


class TradingEngine:
    """Main trading engine."""
    
    def __init__(
        self,
        binance_client: BinanceClient,
        database: Database,
        risk_manager: RiskManager,
        price_predictor: PricePredictor,
        notification_manager: Optional[NotificationManager] = None,
        trading_enabled: bool = False
    ):
        """
        Initialize trading engine.
        
        Args:
            binance_client: Binance API client
            database: Database instance
            risk_manager: Risk manager instance
            price_predictor: Price predictor instance
            notification_manager: Notification manager instance
            trading_enabled: Whether trading is enabled
        """
        self.binance_client = binance_client
        self.database = database
        self.risk_manager = risk_manager
        self.price_predictor = price_predictor
        self.notification_manager = notification_manager
        self.trading_enabled = trading_enabled
        
        self.logger = get_contextual_logger("TradingEngine")
        self.fill_processor = UnifiedFillProcessor(database)
        self.trade_monitor = TradeMonitor(database, binance_client)
        self.running = False
    
    async def process_signal(self, signal):
        """
        Process a scanner signal and execute trade if valid.
        
        Args:
            signal: ScannerSignal object
        """
        if not self.trading_enabled:
            self.logger.debug(f"Trading disabled, skipping signal for {signal.symbol}")
            return
        
        try:
            # Add context for this signal processing
            if hasattr(self.logger, 'context'):
                with self.logger.context(
                    symbol=signal.symbol,
                    signal_id=signal.signal_id,
                    strategy=signal.strategy,
                    signal_type=signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
                ):
                    self.logger.info(f"Processing signal: {signal.signal_type} ({signal.strategy})")
            else:
                self.logger.info(f"Processing signal: {signal.symbol} {signal.signal_type} ({signal.strategy})")
            
            # Get current market data
            ticker = await self.binance_client.get_ticker(signal.symbol)
            order_book = await self.binance_client.get_order_book(signal.symbol)
            klines = await self.database.get_klines(signal.symbol, limit=200)
            
            if not klines:
                self.logger.warning(f"No klines available for {signal.symbol}")
                return
            
            # Get account balance
            from ..core.constants import MIN_BALANCE_USDT
            
            account_balance = await self.binance_client.get_account_balance("USDT")
            
            if account_balance < MIN_BALANCE_USDT:
                self.logger.warning(f"Insufficient account balance: ${account_balance:.2f} < ${MIN_BALANCE_USDT:.2f}")
                return
            
            # Only process BUY signals for now
            if signal.signal_type != "BUY":
                return
            
            # Validate trade with risk manager
            is_valid, reason, stop_loss_price, position_size = self.risk_manager.validate_trade(
                signal.symbol,
                OrderSide.BUY,
                signal.price,
                klines,
                order_book,
                account_balance
            )
            
            if not is_valid:
                self.logger.info(f"Trade rejected for {signal.symbol}: {reason}")
                return
            
            # Get ML prediction (now async)
            ml_prediction = await self.price_predictor.predict(klines)
            
            # Enhanced confidence with ML
            from ..core.constants import MIN_SIGNAL_CONFIDENCE
            
            final_confidence = signal.confidence
            direction = ml_prediction.get('direction')
            ml_confidence = ml_prediction.get('confidence', 0.0)
            
            if direction == 'UP' and ml_confidence > MIN_SIGNAL_CONFIDENCE:
                final_confidence = min(0.95, signal.confidence + ml_confidence * 0.2)
            
            # Execute trade
            if final_confidence > MIN_SIGNAL_CONFIDENCE:
                await self._execute_trade(
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    quantity=position_size,
                    entry_price=signal.price,
                    stop_loss_price=stop_loss_price,
                    strategy=signal.strategy,
                    ml_prediction=ml_prediction
                )
                
                # Record trade for cooldown
                self.risk_manager.record_trade(signal.symbol)
            else:
                self.logger.info(f"Signal confidence too low: {final_confidence:.2f}")
        
        except (ValueError, KeyError, TypeError) as e:
            self.logger.error(f"Data error processing signal: {e}")
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Network error processing signal: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error processing signal: {e}", exc_info=True)
    
    async def _execute_trade(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        entry_price: float,
        stop_loss_price: float,
        strategy: str,
        ml_prediction: Dict[str, Any]
    ):
        """
        Execute a trade with proper error handling and rollback logic.
        
        If order creation succeeds but database insert fails, attempts to cancel
        the order to maintain consistency.
        """
        order = None
        order_created = False
        
        try:
            self.logger.info(
                f"Executing {side.value} order: {symbol} "
                f"qty={quantity:.8f} price={entry_price:.8f}"
            )
            
            # Step 1: Create order on exchange
            try:
                order = await self.binance_client.create_order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=quantity
                )
                order_created = True
                self.logger.info(f"Order created on exchange: {order.binance_order_id}")
            except Exception as e:
                self.logger.error(f"Failed to create order on exchange: {e}")
                raise  # Re-raise to be caught by outer handler
            
            # Step 2: Store order in database
            try:
                order.strategy = strategy
                order.stop_loss_price = stop_loss_price
                order_id = await self.database.insert_order(order)
                order.order_id = order_id
                self.logger.debug(f"Order stored in database: {order_id}")
            except Exception as db_error:
                self.logger.error(
                    f"Failed to store order {order.binance_order_id} in database: {db_error}. "
                    f"Attempting to cancel order on exchange..."
                )
                
                # Attempt to cancel the order to maintain consistency
                if order and order.binance_order_id:
                    try:
                        cancelled = await self.binance_client.cancel_order(
                            symbol=symbol,
                            order_id=order.binance_order_id
                        )
                        if cancelled:
                            self.logger.warning(
                                f"Successfully cancelled order {order.binance_order_id} "
                                f"after database failure"
                            )
                        else:
                            self.logger.error(
                                f"Failed to cancel order {order.binance_order_id} "
                                f"after database failure. Manual intervention may be required."
                            )
                    except Exception as cancel_error:
                        self.logger.error(
                            f"Error cancelling order {order.binance_order_id}: {cancel_error}. "
                            f"CRITICAL: Order exists on exchange but not in database. "
                            f"Manual reconciliation required."
                        )
                
                # Re-raise database error
                raise db_error
            
            # Step 3: Process fill (only if database insert succeeded)
            try:
                await self.fill_processor.process_order_fill(order)
                self.logger.debug(f"Order fill processed: {order.binance_order_id}")
            except Exception as fill_error:
                self.logger.error(
                    f"Failed to process order fill for {order.binance_order_id}: {fill_error}. "
                    f"Order exists in database but fill not processed."
                )
                # Don't raise - order is still valid, just fill processing failed
                # This can be retried later
            
            self.logger.info(
                f"Trade executed successfully: {symbol} {side.value} "
                f"Order ID: {order.binance_order_id}, DB ID: {order.order_id}"
            )
            
            # Step 4: Send trade alert (non-critical, don't fail if this fails)
            if self.notification_manager:
                try:
                    await self.notification_manager.send_trade_alert(
                        symbol=symbol,
                        side=side.value,
                        quantity=quantity,
                        price=entry_price,
                        order_id=order.binance_order_id
                    )
                except Exception as alert_error:
                    self.logger.warning(f"Failed to send trade alert: {alert_error}")
        
        except Exception as e:
            self.logger.error(
                f"Error executing trade for {symbol}: {e}",
                exc_info=True  # Include full traceback
            )
            
            # If order was created but something else failed, log for manual review
            if order_created and order:
                self.logger.critical(
                    f"CRITICAL: Order {order.binance_order_id} was created on exchange "
                    f"but trade execution failed. Status: {order.status.value}. "
                    f"Manual review recommended."
                )
            
            # Re-raise to allow caller to handle
            raise
    
    async def monitor_open_trades(self):
        """Monitor and manage open trades using TradeMonitor."""
        try:
            open_trades = await self.database.get_open_trades()
            
            for trade in open_trades:
                # Get current price
                ticker = await self.binance_client.get_ticker(trade.symbol)
                current_price = ticker.get('price')
                
                if current_price is None:
                    self.logger.warning(f"Could not get current price for {trade.symbol}, skipping")
                    continue
                
                # Check exit conditions using TradeMonitor
                exit_reason = await self.trade_monitor.check_trade_exit_conditions(trade, current_price)
                
                if exit_reason:
                    # Map exit reason to close reason
                    reason_map = {
                        "stop_loss": "STOP_LOSS",
                        "take_profit": "TAKE_PROFIT",
                        "trailing_stop": "TRAILING_STOP"
                    }
                    close_reason = reason_map.get(exit_reason, "EXIT_CONDITION")
                    await self._close_trade(trade, current_price, close_reason)
                    continue
                
                # Check breakeven (using RiskManager - keep this logic here as it depends on risk_manager)
                breakeven_enabled = getattr(self.risk_manager, 'breakeven_enabled', True)
                if breakeven_enabled:
                    if self.risk_manager.should_move_to_breakeven(trade, current_price):
                        breakeven_price = self.risk_manager.calculate_breakeven_price(
                            trade.entry_price,
                            trade.quantity
                        )
                        trade.stop_loss_price = breakeven_price
                        await self.database.update_trade(trade)
                        self.logger.info(f"Moved stop loss to breakeven for {trade.symbol}")
                
                # Update trailing stop using TradeMonitor
                trailing_stop_enabled = getattr(self.risk_manager, 'trailing_stop_enabled', True)
                if trailing_stop_enabled:
                    # Get klines for trailing stop calculation
                    klines = await self.database.get_klines(trade.symbol, limit=200)
                    
                    # Use RiskManager's calculate_trailing_stop for ATR-based calculation
                    new_trailing_stop = self.risk_manager.calculate_trailing_stop(
                        trade,
                        current_price,
                        klines
                    )
                    
                    if new_trailing_stop:
                        trade.trailing_stop_price = new_trailing_stop
                        trade.stop_loss_price = new_trailing_stop
                        await self.database.update_trade(trade)
                        self.logger.debug(f"Updated trailing stop for {trade.symbol}: {new_trailing_stop:.8f}")
        
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Network error monitoring trades: {e}")
        except (ValueError, KeyError) as e:
            self.logger.error(f"Data error monitoring trades: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error monitoring trades: {e}", exc_info=True)
    
    async def _close_trade(self, trade: Trade, exit_price: float, reason: str):
        """Close a trade."""
        try:
            self.logger.info(f"Closing trade {trade.trade_id} ({trade.symbol}): {reason}")
            
            # Create exit order
            exit_order = await self.binance_client.create_order(
                symbol=trade.symbol,
                side=OrderSide.SELL if trade.side == OrderSide.BUY else OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=trade.quantity
            )
            
            # Store exit order
            exit_order.strategy = trade.strategy
            exit_order_id = await self.database.insert_order(exit_order)
            exit_order.order_id = exit_order_id
            
            # Update trade
            trade.exit_order_id = exit_order_id
            trade.exit_price = exit_price
            trade.exit_time = datetime.now()
            trade.status = TradeStatus.STOPPED_OUT if reason == "STOP_LOSS" else TradeStatus.CLOSED
            
            # Calculate PnL
            if trade.side == OrderSide.BUY:
                trade.pnl = (exit_price - trade.entry_price) * trade.quantity
            else:
                trade.pnl = (trade.entry_price - exit_price) * trade.quantity
            
            trade.pnl_percent = (trade.pnl / (trade.entry_price * trade.quantity)) * 100
            trade.fees += exit_order.commission
            
            await self.database.update_trade(trade)
            
            # Update risk manager daily PnL
            self.risk_manager.update_daily_pnl(trade.pnl)
            
            # Process fill
            await self.fill_processor.process_order_fill(exit_order)
        
        except Exception as e:
            self.logger.error(f"Error closing trade: {e}")
    
    async def run(self):
        """Run trading engine monitoring loop."""
        self.running = True
        self.logger.info("Trading engine started")
        
        while self.running:
            try:
                await self.monitor_open_trades()
                # Check every 10 seconds (can be made configurable)
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in trading engine loop: {e}")
                await asyncio.sleep(10)
    
    def stop(self):
        """Stop the trading engine."""
        self.running = False
        self.logger.info("Trading engine stopped")
