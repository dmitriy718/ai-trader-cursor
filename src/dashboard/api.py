"""FastAPI dashboard with real-time visualization."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
import asyncio
import json
from datetime import datetime

from ..core.logger import setup_logger
from ..storage.database import Database
from ..trading.engine import TradingEngine


# Pydantic models for request validation
class ExportRequest(BaseModel):
    """Request model for trade export endpoint."""
    format: str = Field(default="csv", description="Export format")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    @validator('format')
    def validate_format(cls, v):
        """Validate export format."""
        if v not in ['csv', 'json']:
            raise ValueError('Format must be either "csv" or "json"')
        return v


class DashboardAPI:
    """FastAPI dashboard for bot monitoring."""
    
    def __init__(
        self,
        database: Database,
        trading_engine: TradingEngine,
        scanner,
        host: str = "0.0.0.0",
        port: int = 8000,
        cors_origins: List[str] = None
    ):
        """
        Initialize dashboard API.
        
        Args:
            database: Database instance
            trading_engine: Trading engine instance
            scanner: Market scanner instance
            host: API host
            port: API port
            cors_origins: CORS origins
        """
        self.database = database
        self.trading_engine = trading_engine
        self.scanner = scanner
        self.host = host
        self.port = port
        
        self.app = FastAPI(title="AI Trading Bot Dashboard")
        
        # Restrict CORS to specific origins for security
        # Default to localhost for development, require explicit config for production
        default_origins = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ]
        
        allowed_origins = cors_origins if cors_origins and cors_origins != ["*"] else default_origins
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )
        
        self.logger = setup_logger("DashboardAPI")
        self.websocket_connections: List[WebSocket] = []
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/")
        async def root():
            return HTMLResponse(content=self._get_dashboard_html())
        
        @self.app.get("/api/health")
        async def health():
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        
        @self.app.get("/api/stats")
        async def get_stats():
            """Get bot statistics."""
            try:
                open_trades = await self.database.get_open_trades()
                daily_pnl = await self.database.get_daily_pnl()
                
                # Get scanner status
                scanner_status = {
                    'running': self.scanner.running,
                    'symbols': len(self.scanner.symbols),
                    'strategies': {
                        'trend': self.scanner.trend_strategy is not None,
                        'mean_reversion': self.scanner.mean_reversion_strategy is not None,
                        'momentum': self.scanner.momentum_strategy is not None,
                        'breakout': self.scanner.breakout_strategy is not None if hasattr(self.scanner, 'breakout_strategy') else False
                    }
                }
                
                # Get RAM state
                ram_state = self.trading_engine.fill_processor.get_ram_state()
                
                return {
                    'open_trades': len(open_trades) if open_trades else 0,
                    'daily_pnl': float(daily_pnl) if daily_pnl is not None else 0.0,
                    'scanner': scanner_status,
                    'trading_enabled': bool(self.trading_engine.trading_enabled),
                    'ram_state': ram_state if ram_state else {}
                }
            except (AttributeError, KeyError, TypeError) as e:
                self.logger.error(f"Data error getting stats: {e}")
                return {"error": f"Data error: {str(e)}"}
            except Exception as e:
                self.logger.error(f"Unexpected error getting stats: {e}", exc_info=True)
                return {"error": str(e)}
        
        @self.app.get("/api/trades")
        async def get_trades():
            """Get all trades."""
            try:
                open_trades = await self.database.get_open_trades()
                trades_data = []
                for t in open_trades:
                    if not t or not hasattr(t, 'trade_id'):
                        continue
                    trades_data.append({
                        'id': t.trade_id if t.trade_id else None,
                        'symbol': str(t.symbol) if t.symbol else 'UNKNOWN',
                        'side': t.side.value if hasattr(t.side, 'value') else str(t.side),
                        'entry_price': float(t.entry_price) if t.entry_price else 0.0,
                        'exit_price': float(t.exit_price) if t.exit_price else None,
                        'quantity': float(t.quantity) if t.quantity else 0.0,
                        'pnl': float(t.pnl) if t.pnl else 0.0,
                        'pnl_percent': float(t.pnl_percent) if t.pnl_percent else 0.0,
                        'status': t.status.value if hasattr(t.status, 'value') else str(t.status),
                        'strategy': str(t.strategy) if t.strategy else 'unknown',
                        'entry_time': t.entry_time.isoformat() if t.entry_time else None,
                        'exit_time': t.exit_time.isoformat() if t.exit_time else None
                    })
                return {'trades': trades_data}
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                self.logger.error(f"Data error getting trades: {e}")
                return {"error": f"Data error: {str(e)}"}
            except Exception as e:
                self.logger.error(f"Unexpected error getting trades: {e}", exc_info=True)
                return {"error": str(e)}
        
        @self.app.get("/api/signals")
        async def get_signals():
            """Get recent scanner signals."""
            try:
                signals = await self.database.get_unprocessed_signals()
                signals_data = []
                for s in signals[:50]:  # Last 50 signals
                    if not s or not hasattr(s, 'signal_id'):
                        continue
                    signals_data.append({
                        'id': s.signal_id if s.signal_id else None,
                        'symbol': str(s.symbol) if s.symbol else 'UNKNOWN',
                        'strategy': str(s.strategy) if s.strategy else 'unknown',
                        'signal_type': str(s.signal_type) if s.signal_type else 'UNKNOWN',
                        'confidence': float(s.confidence) if s.confidence is not None else 0.0,
                        'price': float(s.price) if s.price else 0.0,
                        'indicators': s.indicators if isinstance(s.indicators, dict) else {},
                        'created_at': s.created_at.isoformat() if s.created_at else None
                    })
                return {'signals': signals_data}
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                self.logger.error(f"Data error getting signals: {e}")
                return {"error": f"Data error: {str(e)}"}
            except Exception as e:
                self.logger.error(f"Unexpected error getting signals: {e}", exc_info=True)
                return {"error": str(e)}
        
        @self.app.get("/api/analytics/pnl")
        async def get_pnl():
            """Get real-time PnL."""
            try:
                from ..analytics.performance import PerformanceAnalytics
                analytics = PerformanceAnalytics(
                    self.database,
                    binance_client=self.trading_engine.binance_client if hasattr(self.trading_engine, 'binance_client') else None
                )
                pnl_data = await analytics.get_real_time_pnl()
                return pnl_data
            except Exception as e:
                self.logger.error(f"Error getting PnL: {e}")
                return {"error": str(e)}
        
        @self.app.get("/api/analytics/export")
        async def export_trades(request: ExportRequest = Query(...)):
            """
            Export trade history with validation.
            
            Args:
                request: ExportRequest model with format, start_date, end_date
            
            Returns:
                CSV or JSON export file
            
            Example:
                GET /api/analytics/export?format=csv&start_date=2024-01-01T00:00:00
            """
            try:
                from ..analytics.performance import PerformanceAnalytics
                analytics = PerformanceAnalytics(self.database)
                export_data = await analytics.export_trade_history(
                    format=request.format,
                    start_date=request.start_date,
                    end_date=request.end_date
                )
                
                from fastapi.responses import Response
                if format.lower() == "csv":
                    return Response(content=export_data, media_type="text/csv",
                                  headers={"Content-Disposition": "attachment; filename=trades.csv"})
                else:
                    return Response(content=export_data, media_type="application/json",
                                  headers={"Content-Disposition": "attachment; filename=trades.json"})
            except Exception as e:
                self.logger.error(f"Error exporting trades: {e}")
                return {"error": str(e)}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()
            self.websocket_connections.append(websocket)
            
            try:
                while True:
                    # Send updates every second
                    stats = await get_stats()
                    await websocket.send_json(stats)
                    await asyncio.sleep(1)
            except WebSocketDisconnect:
                self.websocket_connections.remove(websocket)
    
    def _get_dashboard_html(self) -> str:
        """Get dashboard HTML."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>AI Trading Bot Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e27;
            color: #e0e0e0;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { margin-bottom: 30px; }
        .header h1 { color: #4fc3f7; margin-bottom: 10px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card {
            background: #1a1f3a;
            border-radius: 8px;
            padding: 20px;
            border: 1px solid #2a2f4a;
        }
        .card h2 { color: #81c784; margin-bottom: 15px; font-size: 18px; }
        .stat { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .stat-label { color: #9e9e9e; }
        .stat-value { color: #4fc3f7; font-weight: bold; }
        .positive { color: #81c784; }
        .negative { color: #e57373; }
        .pulse {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #81c784;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .strategy-status { margin: 5px 0; }
        .strategy-name { color: #9e9e9e; }
        .strategy-active { color: #81c784; }
        .strategy-inactive { color: #e57373; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #2a2f4a; }
        th { color: #9e9e9e; font-weight: normal; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AI Trading Bot Dashboard</h1>
            <p>Real-time monitoring and intelligence visualization</p>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>📊 Bot Status</h2>
                <div class="stat">
                    <span class="stat-label">Status:</span>
                    <span class="stat-value"><span class="pulse"></span> Running</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Trading:</span>
                    <span class="stat-value" id="trading-enabled">-</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Open Trades:</span>
                    <span class="stat-value" id="open-trades">-</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Daily PnL:</span>
                    <span class="stat-value" id="daily-pnl">-</span>
                </div>
            </div>
            
            <div class="card">
                <h2>🔍 Scanner Status</h2>
                <div class="stat">
                    <span class="stat-label">Symbols:</span>
                    <span class="stat-value" id="scanner-symbols">-</span>
                </div>
                <div id="strategies-status"></div>
            </div>
            
            <div class="card">
                <h2>💹 Open Trades</h2>
                <div id="trades-list"></div>
            </div>
            
            <div class="card">
                <h2>📡 Recent Signals</h2>
                <div id="signals-list"></div>
            </div>
        </div>
    </div>
    
    <script>
        const ws = new WebSocket('ws://localhost:8000/ws');
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };
        
        function updateDashboard(data) {
            // Update stats
            document.getElementById('trading-enabled').textContent = data.trading_enabled ? 'Enabled' : 'Disabled';
            document.getElementById('open-trades').textContent = data.open_trades || 0;
            document.getElementById('daily-pnl').textContent = '$' + (data.daily_pnl || 0).toFixed(2);
            document.getElementById('daily-pnl').className = 'stat-value ' + (data.daily_pnl >= 0 ? 'positive' : 'negative');
            
            // Update scanner
            if (data.scanner) {
                document.getElementById('scanner-symbols').textContent = data.scanner.symbols || 0;
                
                const strategiesDiv = document.getElementById('strategies-status');
                if (data.scanner.strategies) {
                    strategiesDiv.innerHTML = Object.entries(data.scanner.strategies)
                        .map(([name, active]) => `
                            <div class="strategy-status">
                                <span class="strategy-name">${name}:</span>
                                <span class="${active ? 'strategy-active' : 'strategy-inactive'}">
                                    ${active ? '✓ Active' : '✗ Inactive'}
                                </span>
                            </div>
                        `).join('');
                }
            }
        }
        
        // Fetch initial data
        fetch('/api/stats').then(r => r.json()).then(updateDashboard);
        fetch('/api/trades').then(r => r.json()).then(data => {
            const tradesDiv = document.getElementById('trades-list');
            if (data.trades && data.trades.length > 0) {
                tradesDiv.innerHTML = '<table><tr><th>Symbol</th><th>Side</th><th>Entry</th><th>PnL</th></tr>' +
                    data.trades.map(t => `<tr>
                        <td>${t.symbol}</td>
                        <td>${t.side}</td>
                        <td>$${t.entry_price.toFixed(2)}</td>
                        <td class="${t.pnl >= 0 ? 'positive' : 'negative'}">$${t.pnl.toFixed(2)}</td>
                    </tr>`).join('') + '</table>';
            } else {
                tradesDiv.innerHTML = '<p>No open trades</p>';
            }
        });
        fetch('/api/signals').then(r => r.json()).then(data => {
            const signalsDiv = document.getElementById('signals-list');
            if (data.signals && data.signals.length > 0) {
                signalsDiv.innerHTML = '<table><tr><th>Symbol</th><th>Strategy</th><th>Type</th><th>Confidence</th></tr>' +
                    data.signals.slice(0, 10).map(s => `<tr>
                        <td>${s.symbol}</td>
                        <td>${s.strategy}</td>
                        <td>${s.signal_type}</td>
                        <td>${(s.confidence * 100).toFixed(1)}%</td>
                    </tr>`).join('') + '</table>';
            } else {
                signalsDiv.innerHTML = '<p>No recent signals</p>';
            }
        });
    </script>
</body>
</html>
        """
    
    async def run(self):
        """Run the dashboard server."""
        import uvicorn
        self.logger.info(f"Starting dashboard on {self.host}:{self.port}")
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
