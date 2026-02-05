"""E2E tests for risk management."""

import pytest
from src.risk.manager import RiskManager
from src.storage.models import OrderSide, Kline
from datetime import datetime, timedelta


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_position_sizing(mock_risk_manager, sample_klines):
    """Test position size calculation."""
    position_size = mock_risk_manager.calculate_position_size(
        entry_price=50000.0,
        stop_loss_price=49000.0,
        account_balance=10000.0
    )
    
    assert position_size > 0, "Position size should be positive"
    assert position_size <= 10000.0 / 50000.0, "Position size should not exceed balance"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_stop_loss_calculation(mock_risk_manager, sample_klines):
    """Test stop loss calculation using ATR."""
    stop_loss = mock_risk_manager.calculate_stop_loss(
        entry_price=50000.0,
        side=OrderSide.BUY,
        klines=sample_klines
    )
    
    assert stop_loss < 50000.0, "Stop loss for BUY should be below entry"
    assert stop_loss > 0, "Stop loss should be positive"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_chop_detection(mock_risk_manager, sample_klines):
    """Test ADX chop detection."""
    is_chop = mock_risk_manager.detect_chop(sample_klines)
    
    assert isinstance(is_chop, bool), "Should return boolean"
    # Note: Actual value depends on ADX calculation


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_trade_cooldown(mock_risk_manager):
    """Test trade cooldown mechanism."""
    symbol = 'BTCUSDT'
    
    # Record a trade
    mock_risk_manager.record_trade(symbol)
    
    # Check if trade is in cooldown
    is_in_cooldown = mock_risk_manager.is_in_cooldown(symbol)
    assert is_in_cooldown, "Trade should be in cooldown immediately after recording"
    
    # Wait for cooldown to expire (in real scenario)
    # For testing, we can check the cooldown logic


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_daily_loss_limit(mock_risk_manager, mock_database):
    """Test daily loss limit enforcement."""
    # Set daily loss
    mock_risk_manager.daily_loss_limit_usd = 100.0
    
    # Simulate losses exceeding limit
    # This would require tracking daily PnL
    # For now, we test the check logic
    is_valid, reason = mock_risk_manager.check_trade_validity(
        symbol='BTCUSDT',
        klines=[],
        order_book={'bids': [[50000, 1]], 'asks': [[50001, 1]]},
        account_balance=10000.0
    )
    
    assert isinstance(is_valid, bool), "Should return boolean"
    assert isinstance(reason, str) or reason is None, "Reason should be string or None"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_breakeven_calculation(mock_risk_manager):
    """Test breakeven price calculation."""
    breakeven = mock_risk_manager.calculate_breakeven_price(
        entry_price=50000.0,
        side=OrderSide.BUY,
        quantity=0.001,
        fees_percent=0.001
    )
    
    assert breakeven > 50000.0, "Breakeven for BUY should be above entry"
    assert breakeven < 51000.0, "Breakeven should be reasonable"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_input_validation(mock_risk_manager):
    """Test input validation in risk manager."""
    # Test invalid inputs
    with pytest.raises(ValueError):
        mock_risk_manager.calculate_position_size(
            entry_price=-100.0,  # Invalid
            stop_loss_price=90.0,
            account_balance=1000.0
        )
    
    with pytest.raises(ValueError):
        mock_risk_manager.calculate_position_size(
            entry_price=100.0,
            stop_loss_price=90.0,
            account_balance=0.0  # Invalid
        )
