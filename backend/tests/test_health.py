"""
Health API Endpoint Unit & Integration Tests
"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_check_returns_200():
    """
    Ensure the health check endpoint returns HTTP 200 with required schema fields.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "MARSCOPE" in data["system"]
        assert "version" in data
        assert "timestamp_utc" in data
        assert "engines" in data
        assert data["engines"]["physics"] == "ready"
        assert data["engines"]["geospatial"] == "ready"
        assert data["engines"]["terrain"] == "ready"
        assert data["engines"]["routing"] == "ready"


@pytest.mark.asyncio
async def test_root_endpoint_returns_200():
    """
    Ensure the root endpoint provides system documentation discovery links.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["system"] == "MARSCOPE"
        assert data["health_check"] == "/api/health"
        assert data["planetary_body"] == "Mars"
