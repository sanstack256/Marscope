"""Offline contract tests. All records below are synthetic test fixtures, never NASA data."""
from pathlib import Path
import hashlib

import httpx
import pytest

from app.ingestion import acquisition as acquisition_module
from app.ingestion.acquisition import AcquisitionService
from app.ingestion.imagery import ImageryArchiveService, normalize_atlas_hit, normalize_ode_product, parse_label_content
from app.schemas.imagery import PanoramaEligibility, ProductStage


def test_atlas_normalization_preserves_ids_and_gaps():
    fixture = {
        "_id": "fixture-index-id",
        "_source": {
            "uri": "atlas:pds4:fixture:mission:/bundle/data/TEST.IMG",
            "archive": {"uri": "atlas:pds4:fixture:mission:/bundle/data/TEST.IMG", "name": "TEST.IMG",
                        "mission": "fixture", "instrument": ["testcam"], "size": 12,
                        "md5": "0123456789abcdef0123456789abcdef", "file_extension": "img"},
            "gather": {"pds_archive": {"related": {"browse": {"uri": "atlas:pds4:fixture:mission:/bundle/browse/TEST.PNG"},
                                                          "label": {"uri": "atlas:pds4:fixture:mission:/bundle/data/TEST.xml"}}}},
            "pds4_label": {"pds:Axis_Array/pds:axis_name": ["Line", "Sample"],
                           "pds:Axis_Array/pds:elements": ["10", "20"]},
        },
    }
    product = normalize_atlas_hit(fixture)
    assert product.product_id == "TEST.IMG"
    assert product.original_product_url == "https://pds-imaging.jpl.nasa.gov/data/bundle/data/TEST.IMG"
    assert product.image_height == 10 and product.image_width == 20
    assert product.checksum_algorithm == "MD5"
    assert product.panorama_eligibility is PanoramaEligibility.UNVERIFIED
    assert ProductStage.METADATA in product.stages
    assert "dataset_id" in product.metadata_gaps


def test_product_catalog_merges_by_original_product_id(tmp_path: Path):
    service = ImageryArchiveService(tmp_path / "imagery.json")
    first = normalize_atlas_hit({"_source": {"archive": {"name": "fixture.img"}}})
    service._merge_catalog([first])
    assert service.get("fixture.img") is not None
    assert service.all_products()[0].product_id == "fixture.img"


def test_download_stage_only_marks_archive_checksum_verified(tmp_path: Path):
    service = ImageryArchiveService(tmp_path / "imagery.json")
    product = normalize_atlas_hit({"_source": {"archive": {"name": "fixture.img"}}})
    service._merge_catalog([product])
    service.register_download("fixture.img", tmp_path / "fixture.img", "abc", 10, archive_checksum_verified=False)
    assert ProductStage.DOWNLOADED in service.get("fixture.img").stages
    assert ProductStage.CHECKSUMMED not in service.get("fixture.img").stages
    service.register_download("fixture.img", tmp_path / "fixture.img", "abc", 10, archive_checksum_verified=True)
    assert ProductStage.CHECKSUMMED in service.get("fixture.img").stages


def test_pds3_and_pds4_test_label_fixtures_parse_without_inventing_coordinates():
    pds3_fixture = b'PDS_VERSION_ID = PDS3\nPRODUCT_ID = "FIXTURE_1"\nOBJECT = IMAGE\n LINES = 2\n LINE_SAMPLES = 3\nEND_OBJECT = IMAGE\nEND\n'
    pds4_fixture = b'<Product_Observational xmlns="urn:fixture"><Identification_Area><logical_identifier>fixture:1</logical_identifier></Identification_Area></Product_Observational>'
    p3 = parse_label_content(pds3_fixture)
    p4 = parse_label_content(pds4_fixture)
    assert p3["format"] == "PDS3 ODL" and p3["status"] == "parsed"
    assert p3["fields"]["PRODUCT_ID"] == "FIXTURE_1"
    assert p4["format"] == "PDS4 XML" and p4["fields"]["logical_identifier"] == ["fixture:1"]
    assert "latitude" not in p3["fields"] and "longitude" not in p4["fields"]


def test_ode_test_fixture_keeps_coordinate_convention_and_file_roles():
    fixture = {
        "pdsid": "FIXTURE_RED", "Data_Set_Id": "MRO-M-HIRISE-3-RDR-V1.1", "ihid": "MRO", "iid": "HIRISE",
        "pt": "RDRV11", "Observation_time": "2009-04-04T07:13:46Z", "Center_latitude": "-14.2",
        "Center_longitude": "240.1", "Footprint_GL_geometry": "POLYGON ((240 -14, 241 -14, 240 -14))",
        "Product_files": {"Product_file": [
            {"Type": "Browse", "Description": "BROWSE", "URL": "https://archive.example/browse.jpg"},
            {"Type": "Product", "Description": "PRODUCT DATA FILE", "KBytes": "10", "URL": "https://archive.example/product.jp2"},
            {"Type": "Product", "Description": "PRODUCT LABEL FILE", "URL": "https://archive.example/product.lbl"},
        ]},
    }
    product = normalize_ode_product(fixture)
    assert product.product_id == "FIXTURE_RED" and product.dataset_id == "MRO-M-HIRISE-3-RDR-V1.1"
    assert product.latitude == -14.2 and product.longitude == 240.1
    assert product.coordinate_convention == "planetocentric latitude; east-positive longitude 0–360"
    assert product.original_product_url.endswith("product.jp2")
    assert product.label_url.endswith("product.lbl") and product.browse_image_url.endswith("browse.jpg")
    assert product.archive_file_size_value == 10 and product.archive_file_size_unit == "KBytes"
    assert product.panorama_eligibility is PanoramaEligibility.UNVERIFIED


@pytest.mark.asyncio
async def test_atlas_query_uses_bounded_pagination_and_documented_metadata_filters(tmp_path: Path, monkeypatch):
    import json
    from app.ingestion import imagery as imagery_module
    captured = {}

    def client_factory(timeout_seconds=30):
        async def handler(request):
            captured.update(json.loads(await request.aread()))
            return httpx.Response(200, json={"hits": {"total": {"value": 12, "relation": "eq"}, "hits": []}}, request=request)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(imagery_module, "create_async_http_client", client_factory)
    service = ImageryArchiveService(tmp_path / "catalog.json")
    result = await service.search(mission="MSL", product_type="MDS", sol=184, limit=7, offset=14)
    assert captured["from"] == 14 and captured["size"] == 7
    clauses = captured["query"]["bool"]["filter"]
    serialized = json.dumps(clauses)
    assert "gather.common.product_type" in serialized
    assert "start_sol_number" in serialized
    assert result["total"] == 12 and result["total_relation"] == "eq"


def test_imagery_api_status_and_missing_product_contract(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import imagery as imagery_api
    monkeypatch.setattr(imagery_api, "service", ImageryArchiveService(tmp_path / "catalog.json"))
    with TestClient(app) as client:
        status = client.get("/api/imagery/status")
        missing = client.get("/api/imagery/products/not-a-real-product")
    assert status.status_code == 200
    assert status.json()["catalogue_records"] == 0
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "product_not_catalogued"


@pytest.mark.asyncio
async def test_streaming_acquisition_checks_checksum_and_truncation(tmp_path: Path, monkeypatch):
    payload = b"NASA test fixture bytes"
    expected_md5 = hashlib.md5(payload).hexdigest()

    def client_factory(timeout_seconds=30):
        async def handler(request):
            return httpx.Response(200, content=payload, headers={"content-length": str(len(payload)), "content-type": "application/octet-stream"}, request=request)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)

    monkeypatch.setattr(acquisition_module, "create_async_http_client", client_factory)
    service = AcquisitionService(tmp_path / "raw", tmp_path / "manifests")
    result = await service.download_imagery_file(product_id="fixture.img", source_url="https://pds-imaging.jpl.nasa.gov/data/fixture.img", filename="fixture.img", expected_md5=expected_md5)
    assert result["archive_md5_verified"] is True
    assert Path(result["local_file_path"]).read_bytes() == payload
    reused = await service.download_imagery_file(product_id="fixture.img", source_url="https://pds-imaging.jpl.nasa.gov/data/fixture.img", filename="fixture.img", expected_md5=expected_md5)
    assert reused["reused_verified_file"] is True

    def truncated_client_factory(timeout_seconds=30):
        async def handler(request):
            return httpx.Response(200, content=payload, headers={"content-length": "999", "content-type": "application/octet-stream"}, request=request)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)

    monkeypatch.setattr(acquisition_module, "create_async_http_client", truncated_client_factory)
    with pytest.raises(ValueError, match="Truncated or inconsistent"):
        await service.download_imagery_file(product_id="truncated.img", source_url="https://pds-imaging.jpl.nasa.gov/data/truncated.img", filename="truncated.img")
    assert not (tmp_path / "raw" / "imagery" / "truncated.img").exists()


@pytest.mark.nasa_integration
@pytest.mark.asyncio
async def test_live_ode_navcam_rdr_holdings_report():
    """Run explicitly with NASA_INTEGRATION=1; archive errors are reported as unavailable holdings."""
    import os
    if os.getenv("NASA_INTEGRATION") != "1":
        pytest.skip("NASA integration disabled; set NASA_INTEGRATION=1 to query ODE")
    service = ImageryArchiveService(Path("/tmp/marscope-imagery-integration.json"))
    scopes = [
        ("MSL-M-NAVCAM-5-RDR-V1.0", "RDR"),
        ("MSL-M-NAVCAM-5-RDR-MOSAIC-V1.0", "RDR"),
        ("MSL-M-NAVCAM-2-EDR-V1.0", "EDR"),
    ]
    errors = []
    for dataset_id, product_type in scopes:
        try:
            result = await service.ode_search(instrument_host_id="MSL", instrument_id="NAVCAM",
                                              product_type=product_type, dataset_id=dataset_id, limit=1)
            print(f"required_dataset={dataset_id} found={bool(result['products'])} products={len(result['products'])} downloaded=false checksum_verified=false parsed=false")
        except Exception as exc:
            errors.append(str(exc))
            print(f"required_dataset={dataset_id} found=false downloaded=false checksum_verified=false parsed=false reason={exc}")
    if errors:
        pytest.skip(f"ODE did not support one or more requested MSL Navcam combinations: {errors[0]}")


@pytest.mark.nasa_integration
@pytest.mark.asyncio
async def test_live_atlas_navcam_discovery_report():
    """Check the exact archive filter; never interpret a failed request as an empty result."""
    import os
    if os.getenv("NASA_INTEGRATION") != "1":
        pytest.skip("NASA integration disabled; set NASA_INTEGRATION=1 to query PDS Atlas")
    service = ImageryArchiveService(Path("/tmp/marscope-atlas-integration.json"))
    result = await service.search(mission="msl", instrument="navcam", limit=1)
    print(f"required_dataset=MSL-M-NAVCAM-5-RDR-V1.0 atlas_mission=msl instrument=navcam total={result['total']} relation={result['total_relation']} found={bool(result['products'])} downloaded=false checksum_verified=false parsed=false")
