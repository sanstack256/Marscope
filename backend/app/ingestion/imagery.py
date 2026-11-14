"""NASA imagery archive clients and product-level catalogue.

Uses the public PDS Imaging Atlas Elasticsearch search interface. Search is
bounded and stores only records returned by the archive, with source payloads
retained as provenance. ODE is queried separately by its documented REST client.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.parse import quote

import httpx
import hashlib
import xml.etree.ElementTree as ET

from app.ingestion.http_client import create_async_http_client
from app.schemas.imagery import ImageryProduct, PanoramaEligibility, ProductStage
from app.ingestion.pds_label import parse_pds3_label

logger = logging.getLogger(__name__)
ATLAS_SEARCH_URL = "https://pds-imaging.jpl.nasa.gov/api/search/atlas/_search"
ODE_URL = "https://oderest.rsl.wustl.edu/live2/"


class ArchiveError(RuntimeError):
    pass


def _as_string(value: Any) -> Optional[str]:
    return str(value) if value not in (None, "") else None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _archive_http_url(uri: Any) -> Optional[str]:
    """Atlas URIs are identifiers; map their documented path to PDS IMG data host."""
    if not isinstance(uri, str):
        return None
    if uri.startswith("https://"):
        return uri
    if uri.startswith("atlas:") and ":/" in uri:
        path = uri.split(":/", 1)[1]
        return "https://pds-imaging.jpl.nasa.gov/data/" + quote(path.lstrip("/"), safe="/-._")
    return None


def normalize_atlas_hit(hit: dict[str, Any]) -> ImageryProduct:
    src = hit.get("_source") or {}
    archive = src.get("archive") or {}
    gather = src.get("gather") or {}
    pds = ((gather.get("pds_archive") or {}).get("related") or {})
    browse = pds.get("browse") or {}
    label = pds.get("label") or {}
    size = archive.get("size")
    axes = src.get("pds4_label") or {}
    axis_names = axes.get("pds:Axis_Array/pds:axis_name") or []
    axis_sizes = axes.get("pds:Axis_Array/pds:elements") or []
    axis_map = {str(name).strip().lower(): int(size) for name, size in zip(axis_names, axis_sizes) if str(size).isdigit()}
    observation_time = ((src.get("time") or {}).get("start_time")
                        or (axes.get("msn:Mission_Information/msn:instrument_start_time") or [None])[0])
    sol_raw = (axes.get("msn:Surface_Mission/msn:start_sol_number") or
               axes.get("msn:Surface_Mission/msn:start_local_mean_solar_time_sol") or [None])[0]
    try:
        sol = int(sol_raw) if sol_raw is not None else None
    except (TypeError, ValueError):
        sol = None
    gaps = [k for k, v in (("dataset_id", archive.get("data_set_id")), ("browse", browse.get("uri")), ("label", label.get("uri"))) if not v]
    return ImageryProduct(
        source_archive="NASA PDS Imaging Atlas",
        source_record_uri=_as_string(src.get("uri") or archive.get("uri")),
        mission=_as_string(archive.get("mission")),
        instrument=", ".join(archive.get("instrument", [])) if isinstance(archive.get("instrument"), list) else _as_string(archive.get("instrument")),
        dataset_id=_as_string(archive.get("data_set_id") or src.get("data_set_id")),
        product_id=_as_string(archive.get("name") or src.get("uri") or hit.get("_id")) or "unknown",
        product_type=_as_string((src.get("common") or {}).get("product_type") or archive.get("object_type")),
        observation_time=_as_string(observation_time),
        sol=sol,
        original_product_url=_archive_http_url(archive.get("uri")),
        browse_image_url=_archive_http_url(browse.get("uri")),
        label_url=_archive_http_url(label.get("uri")),
        image_width=axis_map.get("sample"),
        image_height=axis_map.get("line"),
        image_format=_as_string(archive.get("file_extension")),
        camera_model=_as_string((axes.get("geom:Camera_Model_Parameters/geom:model_type") or [None])[0]),
        file_size_bytes=int(size) if size is not None else None,
        checksum=_as_string(archive.get("md5")),
        checksum_algorithm="MD5" if archive.get("md5") else None,
        retrieved_at=datetime.now(timezone.utc),
        stages=[ProductStage.DISCOVERED, ProductStage.METADATA],
        metadata_gaps=gaps,
        provenance={"archive_record": src, "index_id": hit.get("_id")},
    )


def parse_label_content(content: bytes) -> dict[str, Any]:
    """Parse supported PDS labels while preserving unsupported input elsewhere."""
    try:
        root = ET.fromstring(content)
        fields: dict[str, list[str]] = {}
        for element in root.iter():
            if element.text and element.text.strip():
                fields.setdefault(element.tag.split("}")[-1], []).append(element.text.strip())
        return {"format": "PDS4 XML", "status": "parsed", "fields": {"root_tag": root.tag, **fields}}
    except ET.ParseError:
        try:
            fields = parse_pds3_label(content.decode("utf-8", errors="replace"))
            return {"format": "PDS3 ODL", "status": "parsed", "fields": fields}
        except Exception as exc:
            return {"format": "unknown", "status": "unsupported", "error": str(exc), "fields": {}}


def normalize_ode_product(raw: dict[str, Any]) -> ImageryProduct:
    files = (raw.get("Product_files") or {}).get("Product_file") or []
    if isinstance(files, dict):
        files = [files]
    product_file = next((f for f in files if str(f.get("Type", "")).lower() == "product" and "product label file" not in str(f.get("Description", "")).lower()), None)
    label_file = next((f for f in files if "label file" in str(f.get("Description", "")).lower() and "data file" not in str(f.get("Description", "")).lower()), None)
    browse_file = next((f for f in files if str(f.get("Type", "")).lower() == "browse"), None)
    raw_label_url = raw.get("LabelURL")
    if raw_label_url and Path(urlparse(str(raw_label_url)).path).suffix.lower() not in {".lbl", ".xml"}:
        raw_label_url = None
    size_kb = product_file.get("KBytes") if product_file else None
    lat = raw.get("Center_latitude")
    lon = raw.get("Center_longitude")
    has_archive_geometry = lat not in (None, "") and lon not in (None, "") and bool(raw.get("Footprint_GL_geometry") or raw.get("Footprint_geometry"))
    stages = [ProductStage.DISCOVERED, ProductStage.METADATA]
    if has_archive_geometry:
        stages.append(ProductStage.GEO_VERIFIED)
    return ImageryProduct(
        source_archive="Mars Orbital Data Explorer (ODE)",
        source_record_uri=_as_string(raw.get("FilesURL")),
        mission=_as_string(raw.get("ihid")), instrument=_as_string(raw.get("iid")),
        dataset_id=_as_string(raw.get("Data_Set_Id")),
        product_id=_as_string(raw.get("pdsid") or raw.get("ode_id")) or "unknown",
        product_type=_as_string(raw.get("Label_product_type") or raw.get("pt")),
        observation_time=_as_string(raw.get("Observation_time")),
        latitude=_as_float(lat),
        longitude=_as_float(lon),
        coordinate_convention="planetocentric latitude; east-positive longitude 0–360" if lat is not None and lon is not None else None,
        coordinate_reference_system="Mars geographic coordinates; coordinate frame unspecified by ODE response" if lat is not None and lon is not None else None,
        footprint=_as_string(raw.get("Footprint_GL_geometry") or raw.get("Footprint_geometry")),
        projection=_as_string(raw.get("Map_projection_type")),
        processing_level=_as_string(raw.get("pt")),
        original_product_url=_as_string((product_file or {}).get("URL")),
        browse_image_url=_as_string((browse_file or {}).get("URL")),
        label_url=_as_string((label_file or {}).get("URL") or raw_label_url),
        archive_file_size_value=_as_float(size_kb),
        archive_file_size_unit="KBytes" if size_kb is not None else None,
        retrieved_at=datetime.now(timezone.utc),
        stages=stages,
        metadata_gaps=[k for k, v in (("image_dimensions", None), ("label", (label_file or {}).get("URL") or raw.get("LabelURL")),
                                      ("original_product_url", (product_file or {}).get("URL")),
                                      ("footprint", raw.get("Footprint_GL_geometry") or raw.get("Footprint_geometry"))) if not v],
        provenance={"archive_record": raw, "coordinates_source": "ODE indexed product metadata" if lat is not None and lon is not None else None,
                    "geographic_association": "ODE product center and footprint" if has_archive_geometry else None},
    )


class ImageryArchiveService:
    def __init__(self, catalog_path: Path, raw_dir: Optional[Path] = None):
        self.catalog_path = catalog_path.resolve()
        self.raw_dir = (raw_dir or catalog_path.parent.parent / "raw").resolve()
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)

    async def search(self, *, mission: Optional[str] = None, instrument: Optional[str] = None,
                     dataset_id: Optional[str] = None, product_id: Optional[str] = None,
                     product_type: Optional[str] = None, sol: Optional[int] = None,
                     file_extension: str = "img", limit: int = 25, offset: int = 0) -> dict[str, Any]:
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        filters: list[dict[str, Any]] = []
        for key, value in (("archive.mission", mission.lower() if mission else None),
                           ("archive.instrument", instrument.lower() if instrument else None),
                           ("data_set_id", dataset_id), ("archive.name", product_id),
                           ("archive.file_extension", file_extension.lower() if file_extension else None),
                           ("gather.common.product_type", product_type.upper() if product_type else None)):
            if value:
                filters.append({"term": {key: value}})
        if sol is not None:
            sol_term = {"bool": {"should": [
                {"term": {"pds4_label.msn:Surface_Mission/msn:start_sol_number": f"{sol:04d}"}},
                {"term": {"pds4_label.msn:Surface_Mission/msn:start_local_mean_solar_time_sol": str(sol)}},
            ], "minimum_should_match": 1}}
            filters.append(sol_term)
        query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
        async with create_async_http_client(timeout_seconds=30) as client:
            response = await client.post(ATLAS_SEARCH_URL, json={"query": query, "from": offset, "size": limit})
        if response.status_code != 200:
            raise ArchiveError(f"PDS Imaging Atlas HTTP {response.status_code}")
        payload = response.json()
        if payload.get("error"):
            raise ArchiveError(f"PDS Imaging Atlas error: {payload['error']}")
        hits = payload.get("hits", {})
        total_value = hits.get("total", 0)
        total_relation = total_value.get("relation", "eq") if isinstance(total_value, dict) else "eq"
        total = total_value.get("value", 0) if isinstance(total_value, dict) else total_value
        products = [normalize_atlas_hit(hit) for hit in hits.get("hits", [])]
        self._merge_catalog(products)
        return {"source": "NASA PDS Imaging Atlas", "queried_at": datetime.now(timezone.utc),
                "total": total, "total_relation": total_relation, "limit": limit, "offset": offset, "products": products}

    async def ode_search(self, *, instrument_host_id: Optional[str] = None,
                         instrument_id: Optional[str] = None, product_type: Optional[str] = None,
                         dataset_id: Optional[str] = None, product_id: Optional[str] = None,
                         min_latitude: Optional[float] = None, max_latitude: Optional[float] = None,
                         western_longitude: Optional[float] = None, eastern_longitude: Optional[float] = None,
                         location_match: Optional[str] = None,
                         limit: int = 25, offset: int = 0) -> dict[str, Any]:
        """Query documented ODE live2 query=products JSON interface."""
        params = {"target": "mars", "query": "products", "results": "c o p m f", "output": "JSON",
                  "limit": min(max(limit, 1), 100), "offset": max(offset, 0)}
        for key, value in (("ihid", instrument_host_id), ("iid", instrument_id), ("pt", product_type),
                           ("dsid", dataset_id), ("pdsid", product_id)):
            if value:
                params[key] = value
        bounds = {"minlat": min_latitude, "maxlat": max_latitude,
                  "westernlon": western_longitude, "easternlon": eastern_longitude}
        if any(value is not None for value in bounds.values()) and not all(value is not None for value in bounds.values()):
            raise ArchiveError("ODE bounding-box queries require min/max latitude and west/east longitude together")
        if all(value is not None for value in bounds.values()):
            if not (-90 <= min_latitude <= max_latitude <= 90):
                raise ArchiveError("ODE latitude bounds must satisfy -90 <= min <= max <= 90")
            if not (0 <= western_longitude <= 360 and 0 <= eastern_longitude <= 360):
                raise ArchiveError("ODE longitude bounds must use documented positive-east 0–360 degrees")
            params.update(bounds)
            params["loc"] = location_match or "f"
        async with create_async_http_client(timeout_seconds=30) as client:
            response = await client.get(ODE_URL, params=params)
        if response.status_code != 200:
            raise ArchiveError(f"ODE REST HTTP {response.status_code}")
        payload = response.json()
        result = payload.get("ODEResults", {})
        if str(result.get("Status", "")).upper() == "ERROR" or result.get("Error"):
            raise ArchiveError(f"ODE REST error: {result.get('Error', 'unknown archive error')}")
        raw_products = result.get("Products", {}).get("Product", [])
        if isinstance(raw_products, dict):
            raw_products = [raw_products]
        products = [normalize_ode_product(item) for item in raw_products]
        self._merge_catalog(products)
        count = result.get("Count")
        return {"source": "Mars ODE REST", "queried_at": datetime.now(timezone.utc),
                "total": int(count) if str(count).isdigit() else len(products), "limit": params["limit"],
                "offset": params["offset"], "products": products}

    def get(self, product_id: str) -> Optional[ImageryProduct]:
        return self._read_catalog().get(product_id)

    async def retrieve_label(self, product_id: str) -> dict[str, Any]:
        product = self.get(product_id)
        if product is None:
            raise ArchiveError("Product is not catalogued")
        if product.local_label_path and Path(product.local_label_path).is_file():
            cached = Path(product.local_label_path).read_bytes()
            return {**parse_label_content(cached), "local_path": product.local_label_path,
                    "sha256": hashlib.sha256(cached).hexdigest(), "cached": True}
        if not product.label_url:
            raise ArchiveError("Product label URL is unavailable")
        if urlparse(product.label_url).hostname not in {"pds-imaging.jpl.nasa.gov", "planetarydata.jpl.nasa.gov", "hirise.lpl.arizona.edu"}:
            raise ArchiveError("Label URL is outside the verified PDS Imaging host")
        async with create_async_http_client(timeout_seconds=30) as client:
            response = await client.get(product.label_url)
        if response.status_code != 200:
            product.label_parse_status = "retrieval_failed"
            if "label" not in product.metadata_gaps:
                product.metadata_gaps.append("label")
            product.provenance["label"] = {"url": product.label_url, "retrieval_status": response.status_code}
            self._merge_catalog([product])
            raise ArchiveError(f"Label request HTTP {response.status_code}")
        content = response.content
        if not content or len(content) > 20_000_000:
            raise ArchiveError("Label is empty or exceeds the 20 MB metadata safety limit")
        label_path = self.raw_dir / "imagery_labels" / f"{hashlib.sha256(product_id.encode()).hexdigest()[:24]}{Path(product.label_url).suffix}"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        if not label_path.exists():
            label_path.write_bytes(content)
        result = parse_label_content(content)
        product.label_parse_status = result["status"]
        product.local_label_path = str(label_path)
        product.processing_history.append({"action": "retrieve_and_parse_label", "at": datetime.now(timezone.utc).isoformat(),
                                           "format": result["format"], "status": result["status"], "source_url": product.label_url})
        product.metadata_gaps = [g for g in product.metadata_gaps if g != "label"]
        if ProductStage.METADATA not in product.stages:
            product.stages.append(ProductStage.METADATA)
        product.provenance["label"] = {"url": product.label_url, "local_path": str(label_path), "sha256": hashlib.sha256(content).hexdigest(), "parser": result["format"]}
        self._merge_catalog([product])
        return {**result, "local_path": str(label_path), "sha256": hashlib.sha256(content).hexdigest()}

    async def verify_product_url(self, product_id: str) -> dict[str, Any]:
        product = self.get(product_id)
        if product is None or not product.original_product_url:
            raise ArchiveError("Original product URL is unavailable")
        allowed_hosts = {"pds-imaging.jpl.nasa.gov", "planetarydata.jpl.nasa.gov", "hirise.lpl.arizona.edu"}
        if urlparse(product.original_product_url).hostname not in allowed_hosts:
            raise ArchiveError("Product URL is outside the verified PDS IMG hosts")
        async with create_async_http_client(timeout_seconds=30) as client:
            response = await client.head(product.original_product_url)
        accessible = response.status_code == 200
        result = {"http_status": response.status_code, "accessible": accessible,
                  "content_length": int(response.headers["content-length"]) if response.headers.get("content-length", "").isdigit() else None,
                  "resolved_url": str(response.url), "probed_at": datetime.now(timezone.utc).isoformat()}
        if accessible:
            if result["content_length"] is not None:
                product.file_size_bytes = result["content_length"]
            if ProductStage.DOWNLOAD_AVAILABLE not in product.stages:
                product.stages.append(ProductStage.DOWNLOAD_AVAILABLE)
        else:
            product.metadata_gaps.append("product_url_not_retrievable")
        product.provenance["availability_probe"] = result
        product.processing_history.append({"action": "probe_original_product_url", **result})
        self._merge_catalog([product])
        return result

    def register_download(self, product_id: str, local_path: Path, digest: str, size: int,
                          archive_checksum_verified: bool = False) -> ImageryProduct:
        product = self.get(product_id)
        if product is None:
            raise ArchiveError("Product is not catalogued")
        product.local_file_path = str(local_path)
        product.local_sha256_checksum = digest
        product.file_size_bytes = size
        product.processing_history.append({"action": "acquire_original_product", "at": datetime.now(timezone.utc).isoformat(),
                                           "file_size_bytes": size, "sha256": digest,
                                           "archive_checksum_verified": archive_checksum_verified})
        product.provenance["download"] = {"sha256": digest, "downloaded_at": datetime.now(timezone.utc).isoformat()}
        next_stages = [*product.stages, ProductStage.DOWNLOADED]
        if archive_checksum_verified:
            next_stages.append(ProductStage.CHECKSUMMED)
        product.stages = list(dict.fromkeys(next_stages))
        self._merge_catalog([product])
        return product

    def parse_embedded_pds3_label(self, product_id: str) -> dict[str, Any]:
        product = self.get(product_id)
        if product is None or not product.local_file_path:
            raise ArchiveError("An acquired local product is required before parsing an embedded label")
        data_path = Path(product.local_file_path)
        if not data_path.is_absolute():
            data_path = self.raw_dir.parent.parent / data_path
        with data_path.open("rb") as stream:
            prefix = stream.read(20_000_000)
        if not prefix.lstrip().startswith(b"PDS_VERSION_ID"):
            product.label_parse_status = "no_embedded_pds3_label_detected"
            self._merge_catalog([product])
            return {"status": product.label_parse_status}
        match = re.search(rb"(?im)^END\s*(?:\r?\n|$)", prefix)
        if match is None:
            product.label_parse_status = "incomplete_embedded_pds3_label"
            self._merge_catalog([product])
            return {"status": product.label_parse_status}
        label_bytes = prefix[:match.end()]
        label_path = self.raw_dir / "imagery_labels" / f"{hashlib.sha256(product_id.encode()).hexdigest()[:24]}.lbl"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        if not label_path.exists():
            label_path.write_bytes(label_bytes)
        parsed = parse_label_content(label_bytes)
        product.label_parse_status = parsed["status"]
        product.local_label_path = str(label_path)
        product.processing_history.append({"action": "parse_embedded_pds3_label", "at": datetime.now(timezone.utc).isoformat(),
                                           "status": parsed["status"], "source": "original product prefix"})
        product.provenance["embedded_label"] = {"local_path": str(label_path), "sha256": hashlib.sha256(label_bytes).hexdigest(),
                                                   "source": "original product prefix", "parser": parsed["format"]}
        self._merge_catalog([product])
        return {**parsed, "local_path": str(label_path)}

    def all_products(self) -> list[ImageryProduct]:
        return list(self._read_catalog().values())

    def _read_catalog(self) -> dict[str, ImageryProduct]:
        if not self.catalog_path.exists():
            return {}
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return {p.product_id: p for p in (ImageryProduct.model_validate(x) for x in raw)}

    def _merge_catalog(self, products: list[ImageryProduct]) -> None:
        existing = self._read_catalog()
        for product in products:
            prior = existing.get(product.product_id)
            if prior:
                provenance = dict(prior.provenance)
                provenance.update(product.provenance)
                stages = list(dict.fromkeys([*prior.stages, *product.stages]))
                gaps = list(dict.fromkeys([*prior.metadata_gaps, *product.metadata_gaps]))
                history_by_key = {json.dumps(item, sort_keys=True): item for item in [*prior.processing_history, *product.processing_history]}
                product = product.model_copy(update={
                    "local_file_path": prior.local_file_path or product.local_file_path,
                    "local_label_path": prior.local_label_path or product.local_label_path,
                    "local_sha256_checksum": prior.local_sha256_checksum or product.local_sha256_checksum,
                    "file_size_bytes": prior.file_size_bytes if prior.file_size_bytes is not None else product.file_size_bytes,
                    "label_parse_status": prior.label_parse_status if prior.label_parse_status != "not_attempted" else product.label_parse_status,
                    "panorama_eligibility": prior.panorama_eligibility if prior.panorama_eligibility != PanoramaEligibility.UNVERIFIED else product.panorama_eligibility,
                    "stages": stages,
                    "metadata_gaps": gaps,
                    "processing_history": list(history_by_key.values()),
                    "provenance": provenance,
                })
            existing[product.product_id] = product
        tmp = self.catalog_path.with_suffix(".tmp")
        tmp.write_text(json.dumps([p.model_dump(mode="json") for p in existing.values()], indent=2), encoding="utf-8")
        os.replace(tmp, self.catalog_path)
