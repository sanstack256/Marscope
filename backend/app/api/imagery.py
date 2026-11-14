"""Product-level NASA imagery discovery and catalogue endpoints."""
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pathlib import Path
from urllib.parse import urlparse
from fastapi.responses import FileResponse, RedirectResponse
from app.ingestion.imagery import ArchiveError, ImageryArchiveService
from app.services.container import CATALOG_DIR, acquisition_service, RAW_DIR

router = APIRouter(prefix="/imagery", tags=["NASA Imagery"])
service = ImageryArchiveService(CATALOG_DIR / "imagery_products" / "catalog.json", raw_dir=RAW_DIR)


async def _acquire(product_id: str):
    record = service.get(product_id)
    if record is None or not record.original_product_url:
        return
    try:
        record.provenance["acquisition_status"] = {"state": "downloading"}
        service._merge_catalog([record])
        filename = Path(urlparse(record.original_product_url).path).name
        result = await acquisition_service.download_imagery_file(
            product_id=record.product_id, source_url=record.original_product_url, filename=filename,
            expected_md5=record.checksum if record.checksum_algorithm == "MD5" else None,
        )
        service.register_download(record.product_id, Path(result["local_file_path"]), result["sha256_checksum"], result["byte_size"],
                                  archive_checksum_verified=result["archive_md5_verified"])
        if record.label_parse_status != "parsed" and not record.local_label_path:
            try:
                service.parse_embedded_pds3_label(record.product_id)
            except ArchiveError:
                pass
        record = service.get(product_id)
        record.provenance["acquisition_status"] = {"state": "completed", **result}
    except Exception as exc:
        record = service.get(product_id)
        if record:
            record.provenance["acquisition_status"] = {"state": "failed", "reason": str(exc)}
    if record:
        service._merge_catalog([record])


@router.get("/status")
async def imagery_status():
    return {"archives": [
        {"name": "NASA PDS Imaging Atlas", "endpoint": "https://pds-imaging.jpl.nasa.gov/api/search/atlas/_search", "status": "queryable"},
        {"name": "Mars Orbital Data Explorer REST", "endpoint": "https://oderest.rsl.wustl.edu/live2/", "status": "queryable; holdings depend on mission/instrument/product type"},
    ], "catalogue_records": len(service.all_products()),
       "panorama_candidates": sum(p.panorama_eligibility.value != "panorama_eligibility_unverified" for p in service.all_products()),
       "catalogue_file": str(service.catalog_path)}


@router.get("/datasets")
async def imagery_datasets():
    # Dataset metadata remains owned by DatasetCatalogService; this endpoint
    # reports dataset identifiers observed in actual product-level records.
    return sorted({p.dataset_id for p in service.all_products() if p.dataset_id})


@router.get("/search")
async def imagery_search(mission: Optional[str] = None, instrument: Optional[str] = None,
                         dataset_id: Optional[str] = None, product_id: Optional[str] = None,
                         product_type: Optional[str] = None, sol: Optional[int] = Query(None, ge=0),
                         file_extension: str = "img",
                         limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    try:
        return await service.search(mission=mission, instrument=instrument, dataset_id=dataset_id,
                                    product_id=product_id, product_type=product_type, sol=sol,
                                    file_extension=file_extension,
                                    limit=limit, offset=offset)
    except ArchiveError as exc:
        raise HTTPException(status_code=502, detail={"error": "archive_query_failed", "message": str(exc)}) from exc


@router.get("/ode/search")
async def ode_search(instrument_host_id: Optional[str] = None, instrument_id: Optional[str] = None,
                     product_type: Optional[str] = None, dataset_id: Optional[str] = None,
                     product_id: Optional[str] = None, min_latitude: Optional[float] = None,
                     max_latitude: Optional[float] = None, western_longitude: Optional[float] = None,
                     eastern_longitude: Optional[float] = None, location_match: Optional[str] = None,
                     limit: int = Query(25, ge=1, le=100),
                     offset: int = Query(0, ge=0)):
    try:
        return await service.ode_search(instrument_host_id=instrument_host_id, instrument_id=instrument_id,
                                        product_type=product_type, dataset_id=dataset_id,
                                        product_id=product_id, min_latitude=min_latitude, max_latitude=max_latitude,
                                        western_longitude=western_longitude, eastern_longitude=eastern_longitude,
                                        location_match=location_match, limit=limit, offset=offset)
    except ArchiveError as exc:
        raise HTTPException(status_code=502, detail={"error": "archive_query_failed", "message": str(exc)}) from exc


@router.get("/products/{product_id}")
async def imagery_product(product_id: str):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    return record


@router.get("/products/{product_id}/label")
async def imagery_label(product_id: str):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    try:
        return await service.retrieve_label(product_id)
    except ArchiveError as exc:
        raise HTTPException(status_code=502, detail={"error": "label_retrieval_failed", "message": str(exc)}) from exc


@router.get("/products/{product_id}/browse")
async def imagery_browse(product_id: str):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    if not record.browse_image_url or urlparse(record.browse_image_url).scheme != "https":
        raise HTTPException(status_code=404, detail={"error": "browse_unavailable", "product_id": product_id})
    allowed = {"pds-imaging.jpl.nasa.gov", "planetarydata.jpl.nasa.gov", "hirise.lpl.arizona.edu", "ode.rsl.wustl.edu"}
    if urlparse(record.browse_image_url).hostname not in allowed:
        raise HTTPException(status_code=502, detail={"error": "browse_host_untrusted", "product_id": product_id})
    return RedirectResponse(record.browse_image_url, status_code=307)


@router.get("/products/{product_id}/image")
async def imagery_original(product_id: str):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    if record.local_file_path and Path(record.local_file_path).is_file():
        return FileResponse(record.local_file_path, filename=Path(record.local_file_path).name)
    if "download_available" not in {stage.value for stage in record.stages} or not record.original_product_url:
        raise HTTPException(status_code=409, detail={"error": "original_image_not_verified_available", "product_id": product_id})
    return RedirectResponse(record.original_product_url, status_code=307)


@router.post("/products/{product_id}/acquire")
async def acquire_imagery_product(product_id: str, background_tasks: BackgroundTasks):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    if not record.original_product_url:
        raise HTTPException(status_code=409, detail={"error": "original_download_url_unavailable", "product_id": product_id})
    if "download_available" not in {stage.value for stage in record.stages}:
        raise HTTPException(status_code=409, detail={"error": "product_url_not_verified", "message": "Run product verification before acquisition.", "product_id": product_id})
    status = record.provenance.get("acquisition_status", {}).get("state")
    if status in {"queued", "downloading"}:
        return {"product_id": product_id, "status": status}
    if record.local_file_path and status == "completed":
        return {"product_id": product_id, "status": "completed", "file_path": record.local_file_path}
    record.provenance["acquisition_status"] = {"state": "queued"}
    service._merge_catalog([record])
    background_tasks.add_task(_acquire, product_id)
    return {"product_id": product_id, "status": "queued"}


@router.get("/products/{product_id}/acquisition")
async def imagery_acquisition_status(product_id: str):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    return {"product_id": product_id, "status": record.provenance.get("acquisition_status", {"state": "not_requested"}),
            "stages": record.stages, "local_file_path": record.local_file_path,
            "checksum": record.checksum, "checksum_algorithm": record.checksum_algorithm}


@router.post("/products/{product_id}/verify")
async def verify_imagery_product(product_id: str):
    try:
        return {"product_id": product_id, **(await service.verify_product_url(product_id))}
    except ArchiveError as exc:
        raise HTTPException(status_code=502, detail={"error": "product_verification_failed", "message": str(exc)}) from exc


@router.get("/products/{product_id}/eligibility")
async def imagery_eligibility(product_id: str):
    record = service.get(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "product_not_catalogued", "product_id": product_id})
    return {"product_id": product_id, "status": record.panorama_eligibility, "evidence": record.provenance,
            "metadata_gaps": record.metadata_gaps}


@router.get("/panoramas")
async def verified_panoramas():
    return [p for p in service.all_products() if p.panorama_eligibility.value in {"cylindrical_panorama", "other_documented_panorama_projection"}]


@router.get("/coverage")
async def imagery_coverage():
    records = [{"product_id": p.product_id, "dataset_id": p.dataset_id, "source_archive": p.source_archive,
                "footprint": p.footprint, "center": {"latitude": p.latitude, "longitude": p.longitude},
                "coordinate_convention": p.coordinate_convention, "source": p.provenance.get("geographic_association") or p.provenance.get("coordinates_source")}
               for p in service.all_products() if p.footprint is not None]
    return {"status": "available" if records else "coverage_unavailable",
            "products_with_footprints": len(records), "records": records}
