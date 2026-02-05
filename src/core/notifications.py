"""Notification system for alerts and updates."""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError

from .logger import setup_logger


class NotificationManager:
    """Manages notifications via Telegram and other channels."""
    
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        enabled: bool = True
    ):
        """
        Initialize notification manager.
        
        Args:
            telegram_token: Telegram bot token
            telegram_chat_id: Telegram chat ID for notifications
            enabled: Whether notifications are enabled
        """
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.enabled = enabled
        self.logger = setup_logger("NotificationManager")
        self.telegram_bot: Optional[Bot] = None
        
        if self.enabled and self.telegram_token:
            try:
                self.telegram_bot = Bot(token=self.telegram_token)
            except Exception as e:
                self.logger.warning(f"Failed to initialize Telegram bot: {e}")
    
    async def send_telegram_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message via Telegram.
        
        Args:
            message: Message text
            parse_mode: Parse mode (HTML or Markdown)
        
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not self.telegram_bot or not self.telegram_chat_id:
            return False
        
        try:
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            self.logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: Optional[int] = None
    ):
        """Send trade execution alert."""
        emoji = "🟢" if side == "BUY" else "🔴"
        message = f"""
{emoji} <b>Trade Executed</b>

Symbol: {symbol}
Side: {side}
Quantity: {quantity:.8f}
Price: ${price:.8f}
Order ID: {order_id or 'N/A'}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        await self.send_telegram_message(message)
    
    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "WARNING"
    ):
        """Send risk limit breach alert."""
        emoji = "⚠️" if severity == "WARNING" else "🚨"
        alert_message = f"""
{emoji} <b>Risk Alert: {alert_type}</b>

{message}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        await self.send_telegram_message(alert_message)
    
    async def send_daily_report(
        self,
        daily_pnl: float,
        trades_count: int,
        win_rate: float,
        total_fees: float
    ):
        """Send daily performance report."""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        message = f"""
{pnl_emoji} <b>Daily Report</b>

PnL: ${daily_pnl:.2f}
Trades: {trades_count}
Win Rate: {win_rate:.1f}%
Total Fees: ${total_fees:.2f}
Date: {datetime.now().strftime('%Y-%m-%d')}
        """.strip()
        
        await self.send_telegram_message(message)
    
    async def send_price_alert(
        self,
        symbol: str,
        current_price: float,
        threshold_price: float,
        direction: str
    ):
        """Send price alert."""
        emoji = "📊"
        direction_text = "above" if direction == "up" else "below"
        message = f"""
{emoji} <b>Price Alert</b>

{symbol} is {direction_text} ${threshold_price:.8f}
Current Price: ${current_price:.8f}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        await self.send_telegram_message(message)
    
    async def send_system_alert(self, message: str, severity: str = "INFO"):
        """Send system alert."""
        emoji_map = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "SUCCESS": "✅"
        }
        emoji = emoji_map.get(severity, "ℹ️")
        
        alert_message = f"""
{emoji} <b>System Alert</b>

{message}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        await self.send_telegram_message(alert_message)
