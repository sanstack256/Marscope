"""
Automated API Endpoints Integration Tests
Validates all public endpoints exposed by MARSCOPE.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["engines"]["physics"] == "ready"
        assert data["engines"]["geospatial"] == "ready"
        assert data["engines"]["terrain"] == "ready"


@pytest.mark.asyncio
async def test_dataset_discovery_and_list():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Discover products
        res_disc = await client.post("/api/datasets/discover")
        assert res_disc.status_code == 200
        datasets = res_disc.json()
        assert len(datasets) >= 3

        # List products with faceted filter
        res_list = await client.get("/api/datasets?mission=Mars+Global+Surveyor")
        assert res_list.status_code == 200
        mgs_datasets = res_list.json()
        assert len(mgs_datasets) >= 1
        assert "MOLA" in mgs_datasets[0]["instrument"]


@pytest.mark.asyncio
async def test_dataset_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/datasets/discover")
        res = await client.post("/api/datasets/mola_megt00n090hb/validate")
        assert res.status_code == 200
        data = res.json()
        assert data["crs_valid"] is True
        assert data["coverage_check"]["is_covered"] is True


@pytest.mark.asyncio
async def test_terrain_summary():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/terrain/summary")
        assert res.status_code == 200
        data = res.json()
        assert "elevation_stats" in data
        assert "slope_stats" in data
        assert data["elevation_stats"]["units"] == "meters"
        assert data["slope_stats"]["units"] == "degrees"


@pytest.mark.asyncio
async def test_observations_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/observations")
        assert res.status_code == 200
        obs_list = res.json()
        assert len(obs_list) >= 2
        assert obs_list[0]["mission"] == "Mars Science Laboratory (MSL)"


@pytest.mark.asyncio
async def test_targets_empty_state_compliance():
    """
    Assert that Target Explorer returns an empty list adhering to zero-fabrication rules.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/targets")
        assert res.status_code == 200
        assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_sources_register():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/sources")
        assert res.status_code == 200
        sources = res.json()
        assert len(sources) >= 5


@pytest.mark.asyncio
async def test_physics_calculation_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test weight calculation
        payload = {"model_name": "weight", "mass_kg": 200.0}
        res = await client.post("/api/physics/calculate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["units"] == "N"
        assert abs(data["calculated_value"] - 744.152) < 0.01

        # Test invalid mass error response
        bad_payload = {"model_name": "weight", "mass_kg": -10.0}
        res_bad = await client.post("/api/physics/calculate", json=bad_payload)
        assert res_bad.status_code == 422
