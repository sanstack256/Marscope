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


def test_split_deployment_manifests_consistent() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    vercel_cfg = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))
    assert "services" not in vercel_cfg, "Vercel must host only the Next.js frontend"
    assert vercel_cfg["framework"] == "nextjs"
    assert "frontend" in vercel_cfg["installCommand"]
    assert "frontend" in vercel_cfg["buildCommand"]
    assert vercel_cfg["outputDirectory"] == "frontend/.next"

    railway_cfg = json.loads((repo_root / "railway.json").read_text(encoding="utf-8"))
    assert railway_cfg["build"]["builder"] == "DOCKERFILE"
    assert railway_cfg["build"]["dockerfilePath"] == "backend/Dockerfile"
    assert railway_cfg["deploy"]["healthcheckPath"] == "/api/health"

    dockerfile_text = (repo_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "MARSCOPE_DATASETS_DIR=/data/datasets" in dockerfile_text
    assert "/app/backend/start.sh" in dockerfile_text
    assert "/api/health" in dockerfile_text

    start_sh_text = (repo_root / "backend" / "start.sh").read_text(encoding="utf-8")
    assert "--host 0.0.0.0" in start_sh_text
    assert "${PORT:-8000}" in start_sh_text
    assert "seed_catalog_metadata_if_empty" in start_sh_text

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


def test_seed_catalog_metadata_without_fabricating_data(tmp_path: Path) -> None:
    from app.ingestion.bootstrap import seed_catalog_metadata_if_empty, verify_local_datasets

    volume_ds = tmp_path / "datasets"
    result = seed_catalog_metadata_if_empty(datasets_dir=volume_ds)
    assert (volume_ds / "bootstrap_manifest.json").is_file()
    assert (volume_ds / "catalog" / "hirise_dteec_009149_1750.json").is_file()
    assert "bootstrap_manifest.json" in result["copied_files"]
    # Must NOT fabricate raw or processed NASA data files
    assert list((volume_ds / "raw").iterdir()) == []
    assert list((volume_ds / "processed").iterdir()) == []

    report = verify_local_datasets(datasets_dir=volume_ds, strict=False)
    assert report.verified_count == 0
    assert report.missing_mandatory_count > 0
    strict_report = verify_local_datasets(datasets_dir=volume_ds, strict=True)
    assert strict_report.preflight_passed is False


def test_production_signing_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config, security

    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "MARSCOPE_SECRET_KEY", "")
    monkeypatch.delenv("MARSCOPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MARSCOPE_SECRET_KEY"):
        security.get_signing_secret()

    monkeypatch.setenv("MARSCOPE_SECRET_KEY", "a" * 32)
    assert security.get_signing_secret() == b"a" * 32
