"""E2E tests for dashboard API."""

import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_health_endpoint(dashboard_setup):
    """Test dashboard health endpoint."""
    async with AsyncClient(app=dashboard_setup.app, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_stats_endpoint(dashboard_setup, mock_database):
    """Test dashboard stats endpoint."""
    async with AsyncClient(app=dashboard_setup.app, base_url="http://test") as client:
        response = await client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "open_trades" in data
        assert "daily_pnl" in data
        assert "scanner" in data
        assert "trading_enabled" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_trades_endpoint(dashboard_setup, mock_database):
    """Test dashboard trades endpoint."""
    async with AsyncClient(app=dashboard_setup.app, base_url="http://test") as client:
        response = await client.get("/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert isinstance(data["trades"], list)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_signals_endpoint(dashboard_setup, mock_database, sample_signal):
    """Test dashboard signals endpoint."""
    # Insert a signal
    await mock_database.insert_signal(sample_signal)
    
    async with AsyncClient(app=dashboard_setup.app, base_url="http://test") as client:
        response = await client.get("/api/signals")
        assert response.status_code == 200
        data = response.json()
        assert "signals" in data
        assert isinstance(data["signals"], list)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_export_endpoint(dashboard_setup, mock_database):
    """Test dashboard export endpoint with validation."""
    async with AsyncClient(app=dashboard_setup.app, base_url="http://test") as client:
        # Test CSV export
        response = await client.get("/api/analytics/export?format=csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        
        # Test JSON export
        response = await client.get("/api/analytics/export?format=json")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        
        # Test invalid format
        response = await client.get("/api/analytics/export?format=invalid")
        assert response.status_code == 422  # Validation error


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_pnl_endpoint(dashboard_setup, mock_database):
    """Test dashboard PnL endpoint."""
    async with AsyncClient(app=dashboard_setup.app, base_url="http://test") as client:
        response = await client.get("/api/analytics/pnl")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dashboard_websocket_connection(dashboard_setup):
    """Test dashboard WebSocket connection."""
    from fastapi.testclient import TestClient
    
    client = TestClient(dashboard_setup.app)
    
    with client.websocket_connect("/ws") as websocket:
        # Should receive initial stats
        data = websocket.receive_json()
        assert "open_trades" in data or "error" in data
