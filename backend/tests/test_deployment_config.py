"""
Deployment Configuration, CORS Security, Routing & Dependency Manifest Tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, _default_cors_origins, _parse_cors_origins
from app.main import app


def test_cors_origin_parsing_and_wildcard_rejection() -> None:
    assert _parse_cors_origins('["https://marscope.example.com", "https://preview.example.com/"]') == [
        "https://marscope.example.com",
        "https://preview.example.com",
    ]
    assert _parse_cors_origins("https://a.example.com, https://b.example.com/") == [
        "https://a.example.com",
        "https://b.example.com",
    ]

    with pytest.raises(ValueError, match="Wildcard"):
        _parse_cors_origins(["*"])
    with pytest.raises(ValueError, match="Wildcard"):
        _parse_cors_origins("*")
    with pytest.raises(ValueError, match="Wildcard"):
        Settings(CORS_ORIGINS=["https://*.example.com"])


def test_vercel_origin_derivation_without_hardcoded_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "marscope-prod.vercel.app")
    monkeypatch.setenv("VERCEL_URL", "marscope-git-main.vercel.app")
    monkeypatch.delenv("VERCEL_BRANCH_URL", raising=False)

    origins = _default_cors_origins()
    assert origins == [
        "https://marscope-prod.vercel.app",
        "https://marscope-git-main.vercel.app",
    ]


@pytest.mark.asyncio
async def test_api_root_docs_and_health_routes() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/", "/api", "/api/health", "/api/health/readiness", "/api/docs", "/api/redoc", "/api/openapi.json"):
            resp = await client.get(path)
            assert resp.status_code == 200, f"Expected 200 for {path}, got {resp.status_code}"

        api_root = (await client.get("/api")).json()
        assert api_root["documentation"] == "/api/docs"
        assert api_root["health_check"] == "/api/health"


def test_vercel_json_and_backend_manifests_consistent() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    vercel_cfg = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))
    assert vercel_cfg["services"]["frontend"]["root"] == "frontend/"
    assert vercel_cfg["services"]["frontend"]["framework"] == "nextjs"
    assert vercel_cfg["services"]["backend"]["root"] == "backend/"
    assert vercel_cfg["services"]["backend"]["framework"] == "fastapi"
    assert vercel_cfg["services"]["backend"]["entrypoint"] == "app.main:app"

    rewrites = vercel_cfg["rewrites"]
    assert rewrites[0]["source"] == "/api/:path*"
    assert rewrites[0]["destination"] == {"service": "backend"}
    assert rewrites[1]["source"] == "/(.*)"
    assert rewrites[1]["destination"] == {"service": "frontend"}

    pyproject_text = (repo_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    req_text = (repo_root / "backend" / "requirements.txt").read_text(encoding="utf-8")
    for pkg in (
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic-settings",
        "httpx",
        "certifi",
        "pillow",
        "numpy",
        "scipy",
        "rasterio",
        "shapely",
        "pyproj",
        "affine",
        "tifffile",
        "networkx",
    ):
        assert pkg in pyproject_text, f"Missing {pkg} in backend/pyproject.toml"
        assert pkg in req_text, f"Missing {pkg} in backend/requirements.txt"
