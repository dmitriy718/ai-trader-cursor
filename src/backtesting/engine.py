"""Historical backtesting engine."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict

from ..core.logger import setup_logger
from ..storage.models import Kline, Trade, OrderSide, TradeStatus
from ..storage.database import Database
from ..api.binance_client import BinanceClient


class BacktestResult:
    """Backtest result container."""
    
    def __init__(self):
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.daily_returns: List[float] = []
        self.total_pnl: float = 0.0
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.win_rate: float = 0.0
        self.profit_factor: float = 0.0
        self.max_drawdown: float = 0.0
        self.sharpe_ratio: float = 0.0
        self.start_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None


class BacktestingEngine:
    """Historical backtesting engine."""
    
    def __init__(
        self,
        database: Database,
        binance_client: BinanceClient,
        initial_balance: float = 10000.0,
        commission_rate: float = 0.001
    ):
        """
        Initialize backtesting engine.
        
        Args:
            database: Database instance
            binance_client: Binance API client
            initial_balance: Initial balance for backtesting
            commission_rate: Commission rate
        """
        self.database = database
        self.binance_client = binance_client
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.logger = setup_logger("BacktestingEngine")
    
    async def run_backtest(
        self,
        symbol: str,
        strategy_func: Callable,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1m"
    ) -> BacktestResult:
        """
        Run backtest for a strategy.
        
        Args:
            symbol: Trading pair symbol
            strategy_func: Strategy function that returns signals
            start_date: Backtest start date
            end_date: Backtest end date
            interval: Kline interval
        
        Returns:
            BacktestResult object
        """
        try:
            self.logger.info(f"Starting backtest for {symbol} from {start_date} to {end_date}")
            
            result = BacktestResult()
            result.start_date = start_date
            result.end_date = end_date
            
            # Fetch historical klines
            klines = await self._fetch_historical_klines(symbol, start_date, end_date, interval)
            
            if len(klines) < 100:
                self.logger.warning(f"Insufficient data for backtest: {len(klines)} klines")
                return result
            
            # Simulate trading
            balance = self.initial_balance
            position = None
            equity_curve = [balance]
            
            for i in range(100, len(klines)):
                current_klines = klines[:i+1]
                current_price = klines[i].close_price
                
                # Get strategy signal
                signal = strategy_func(current_klines)
                
                if signal and signal.get('action') == 'BUY' and position is None:
                    # Open position
                    quantity = balance * 0.1 / current_price  # Use 10% of balance
                    commission = quantity * current_price * self.commission_rate
                    
                    if balance >= quantity * current_price + commission:
                        position = {
                            'entry_price': current_price,
                            'quantity': quantity,
                            'entry_time': klines[i].open_time,
                            'stop_loss': signal.get('stop_loss'),
                            'take_profit': signal.get('take_profit')
                        }
                        balance -= (quantity * current_price + commission)
                
                elif position:
                    # Check exit conditions
                    should_exit = False
                    exit_reason = None
                    
                    if signal and signal.get('action') == 'SELL':
                        should_exit = True
                        exit_reason = "Signal"
                    elif position.get('stop_loss') and current_price <= position['stop_loss']:
                        should_exit = True
                        exit_reason = "Stop Loss"
                    elif position.get('take_profit') and current_price >= position['take_profit']:
                        should_exit = True
                        exit_reason = "Take Profit"
                    
                    if should_exit:
                        # Close position
                        revenue = position['quantity'] * current_price
                        commission = revenue * self.commission_rate
                        balance += (revenue - commission)
                        
                        pnl = revenue - (position['quantity'] * position['entry_price']) - commission * 2
                        
                        trade = Trade(
                            trade_id=None,
                            symbol=symbol,
                            entry_order_id=None,
                            exit_order_id=None,
                            entry_price=position['entry_price'],
                            exit_price=current_price,
                            quantity=position['quantity'],
                            side=OrderSide.BUY,
                            status=TradeStatus.CLOSED,
                            pnl=pnl,
                            pnl_percent=(pnl / (position['quantity'] * position['entry_price'])) * 100,
                            fees=commission * 2,
                            strategy="backtest",
                            entry_time=position['entry_time'],
                            exit_time=klines[i].open_time
                        )
                        
                        result.trades.append(trade)
                        position = None
                
                # Update equity curve
                current_equity = balance
                if position:
                    current_equity += position['quantity'] * current_price
                equity_curve.append(current_equity)
            
            # Calculate metrics
            result.equity_curve = equity_curve
            result.total_trades = len(result.trades)
            result.winning_trades = sum(1 for t in result.trades if t.pnl > 0)
            result.losing_trades = sum(1 for t in result.trades if t.pnl < 0)
            result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0
            result.total_pnl = equity_curve[-1] - self.initial_balance
            
            # Calculate profit factor
            total_profit = sum(t.pnl for t in result.trades if t.pnl > 0)
            total_loss = abs(sum(t.pnl for t in result.trades if t.pnl < 0))
            result.profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            # Calculate max drawdown
            peak = equity_curve[0]
            max_dd = 0
            for equity in equity_curve:
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100
                if dd > max_dd:
                    max_dd = dd
            result.max_drawdown = max_dd
            
            # Calculate Sharpe ratio (simplified)
            if len(equity_curve) > 1:
                returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1] 
                          for i in range(1, len(equity_curve))]
                if returns:
                    avg_return = sum(returns) / len(returns)
                    std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                    result.sharpe_ratio = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0
            
            self.logger.info(
                f"Backtest complete: {result.total_trades} trades, "
                f"Win rate: {result.win_rate:.1f}%, PnL: ${result.total_pnl:.2f}"
            )
            
            return result
        
        except Exception as e:
            self.logger.error(f"Error running backtest: {e}")
            raise
    
    async def _fetch_historical_klines(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str
    ) -> List[Kline]:
        """Fetch historical klines for backtesting."""
        # Try to get from database first
        klines = await self.database.get_klines(symbol, limit=1000)
        
        # Filter by date range
        filtered = [k for k in klines if start_date <= k.open_time <= end_date]
        
        if len(filtered) < 100:
            # Fetch from exchange if not enough data
            self.logger.info(f"Fetching historical data from exchange for {symbol}")
            try:
                klines = await self.binance_client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=1000,
                    end_time=end_date
                )
                # Store in database
                await self.database.insert_klines(klines)
                filtered = [k for k in klines if start_date <= k.open_time <= end_date]
            except Exception as e:
                self.logger.error(f"Error fetching historical klines: {e}")
        
        return filtered
