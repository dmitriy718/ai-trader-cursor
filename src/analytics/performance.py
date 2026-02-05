"""Performance analytics and PnL tracking."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from ..core.logger import setup_logger
from ..storage.database import Database
from ..storage.models import Trade, TradeStatus
from ..api.binance_client import BinanceClient


class PerformanceAnalytics:
    """Performance analytics and real-time PnL tracking."""
    
    def __init__(self, database: Database, binance_client: Optional[BinanceClient] = None):
        """
        Initialize performance analytics.
        
        Args:
            database: Database instance
            binance_client: Optional Binance client for real-time prices
        """
        self.database = database
        self.binance_client = binance_client
        self.logger = setup_logger("PerformanceAnalytics")
        self._pnl_cache: Dict[str, float] = {}
        self._last_update = datetime.now()
    
    async def get_real_time_pnl(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get real-time PnL for open trades.
        
        Args:
            symbol: Optional symbol filter
        
        Returns:
            Dict with PnL data
        """
        try:
            open_trades = await self.database.get_open_trades(symbol)
            
            total_pnl = 0.0
            total_pnl_percent = 0.0
            unrealized_pnl = 0.0
            realized_pnl = 0.0
            
            trade_details = []
            
            for trade in open_trades:
                # Get current price from exchange if available
                current_price = trade.entry_price  # Default to entry price
                if self.binance_client:
                    try:
                        ticker = await self.binance_client.get_ticker(trade.symbol)
                        if ticker and isinstance(ticker, dict):
                            price = ticker.get('price')
                            if price is not None:
                                try:
                                    current_price = float(price)
                                except (ValueError, TypeError):
                                    self.logger.warning(f"Invalid price format for {trade.symbol}: {price}")
                        else:
                            self.logger.debug(f"Invalid ticker response for {trade.symbol}")
                    except (ConnectionError, TimeoutError) as e:
                        self.logger.debug(f"Network error fetching price for {trade.symbol}: {e}")
                    except (KeyError, ValueError, TypeError) as e:
                        self.logger.debug(f"Data error fetching price for {trade.symbol}: {e}")
                    except Exception as e:
                        self.logger.debug(f"Unexpected error fetching price for {trade.symbol}: {e}")
                
                if trade.side.value == "BUY":
                    unrealized = (current_price - trade.entry_price) * trade.quantity
                else:
                    unrealized = (trade.entry_price - current_price) * trade.quantity
                
                unrealized_pnl += unrealized
                trade_details.append({
                    'symbol': trade.symbol,
                    'side': trade.side.value,
                    'entry_price': trade.entry_price,
                    'current_price': current_price,
                    'quantity': trade.quantity,
                    'unrealized_pnl': unrealized,
                    'unrealized_pnl_percent': (unrealized / (trade.entry_price * trade.quantity)) * 100
                })
            
            # Get realized PnL from closed trades
            # This would require a query for closed trades
            # For now, use daily PnL as approximation
            daily_pnl = await self.database.get_daily_pnl()
            realized_pnl = daily_pnl if daily_pnl < 0 else 0  # Only losses realized
            
            total_pnl = unrealized_pnl + realized_pnl
            
            return {
                'total_pnl': total_pnl,
                'unrealized_pnl': unrealized_pnl,
                'realized_pnl': realized_pnl,
                'open_trades_count': len(open_trades),
                'trades': trade_details,
                'last_update': datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error calculating real-time PnL: {e}")
            return {
                'total_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'realized_pnl': 0.0,
                'open_trades_count': 0,
                'trades': [],
                'last_update': datetime.now().isoformat()
            }
    
    async def get_performance_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
        
        Returns:
            Dict with performance metrics
        """
        try:
            # This would require querying closed trades
            # For now, return basic structure
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'total_pnl': 0.0,
                'total_fees': 0.0,
                'net_pnl': 0.0
            }
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {e}")
            return {}
    
    async def export_trade_history(
        self,
        format: str = "csv",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> str:
        """
        Export trade history to CSV or JSON.
        
        Args:
            format: Export format ('csv' or 'json')
            start_date: Start date filter
            end_date: End date filter
        
        Returns:
            Exported data as string
        """
        try:
            import csv
            import json
            import io
            
            # Get all trades (would need to query closed trades too)
            open_trades = await self.database.get_open_trades()
            
            trades_data = []
            for trade in open_trades:
                trades_data.append({
                    'trade_id': trade.trade_id,
                    'symbol': trade.symbol,
                    'side': trade.side.value,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'quantity': trade.quantity,
                    'pnl': trade.pnl,
                    'pnl_percent': trade.pnl_percent,
                    'fees': trade.fees,
                    'strategy': trade.strategy,
                    'status': trade.status.value,
                    'entry_time': trade.entry_time.isoformat() if trade.entry_time else None,
                    'exit_time': trade.exit_time.isoformat() if trade.exit_time else None
                })
            
            if format.lower() == "csv":
                output = io.StringIO()
                if trades_data:
                    writer = csv.DictWriter(output, fieldnames=trades_data[0].keys())
                    writer.writeheader()
                    writer.writerows(trades_data)
                return output.getvalue()
            else:  # JSON
                return json.dumps(trades_data, indent=2)
        
        except Exception as e:
            self.logger.error(f"Error exporting trade history: {e}")
            return ""
