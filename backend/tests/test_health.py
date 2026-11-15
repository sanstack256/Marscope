"""
Health API Endpoint Unit & Integration Tests
"""

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_check_truthful_routing_with_and_without_local_dem(monkeypatch: pytest.MonkeyPatch):
    """
    Ensure /api/health reports `ready` when a processed DEM is locally available
    and `ready_no_local_dem` when no local processed DEM exists.
    """
    from app.api import health as health_mod

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. No local processed DEM -> must NOT claim full routing readiness
        monkeypatch.setattr(health_mod.catalog_service, "list_datasets", lambda: [])
        resp_no_dem = await client.get("/api/health")
        assert resp_no_dem.status_code == 200
        data_no_dem = resp_no_dem.json()
        assert data_no_dem["status"] == "healthy"
        assert data_no_dem["engines"]["physics"] == "ready"
        assert data_no_dem["engines"]["geospatial"] == "ready"
        assert data_no_dem["engines"]["terrain"] == "ready"
        assert data_no_dem["engines"]["routing"] == "ready_no_local_dem"

        # 2. Local processed DEM present and resolvable -> routing == "ready"
        monkeypatch.setattr(
            health_mod.catalog_service,
            "list_datasets",
            lambda: [SimpleNamespace(processed_file_path="processed/mock_dem.tif", failure_reason=None)],
        )
        monkeypatch.setattr(
            health_mod.catalog_service,
            "_resolve_existing_path",
            lambda p: p,
        )
        resp_with_dem = await client.get("/api/health")
        assert resp_with_dem.status_code == 200
        data_with_dem = resp_with_dem.json()
        assert data_with_dem["engines"]["routing"] == "ready"


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
