"""
MARSCOPE Persistent SQLite Spatial Composition Index
Martian Surface Intelligence & Exploration System

Stores validated geochemical and mineralogical CompositionEvidence in SQLite with:
  - R*Tree spatial MBR indexing (plus B-tree fallback) in IAU2000 [0, 360) East longitude
  - Atomic generation cutover (failed builds never corrupt active index)
  - SHA-256 source-file checksum tracking and drift detection
  - Persisted validation audits and rejected-record logs
  - Automatic full or incremental discovery across raw NASA PDS artifacts
"""

from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple
from app.geospatial.crs import normalize_longitude_360
from app.ingestion.pds_label import extract_pds3_metadata, parse_pds4_table_delimited
from app.science.composition.adapters import (
    ApxsEvidenceAdapter,
    CheMinEvidenceAdapter,
    ChemCamEvidenceAdapter,
    CrismEvidenceAdapter,
    EnvironmentalExclusionAdapter,
)
from app.science.composition.models import (
    CompositionEvidence,
    CompositionIndexStatus,
    GenerationBuildStatus,
    IntegrityStatus,
    ProductAuditEntry,
    RejectionRecord,
    RightsStatus,
    SourceArtifactRecord,
)
from app.science.composition.ranking import DEFAULT_HEURISTIC_RANKING_CONFIG
from app.science.composition.validation import (
    EVIDENCE_ID_DETERMINISM_VERSION,
    compute_deterministic_evidence_id,
)
from app.science.coordinate_association import CoordinateAssociationService


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


EXPECTED_COMPOSITION_PRODUCTS: List[Dict[str, Any]] = [
    {
        "dataset_id": "jpl_msl_traverse_waypoints",
        "product_id": "MSL_WAYPOINTS",
        "filename": "msl_waypoints.json",
        "companion_pattern": None,
        "role": "localization_reference",
        "url": "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json",
    },
    {
        "dataset_id": "msl_apxs_supplement_sols_0_3076",
        "product_id": "DS01_2021JE007171R",
        "filename": "ds01_2021je007171r.csv",
        "companion_pattern": "ds01_2021je007171r.xml",
        "role": "composition_table",
        "url": "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/ds01_2021je007171r.csv",
    },
    {
        "dataset_id": "msl_chemcam_moc_0000_0089",
        "product_id": "MOC_0000_0089",
        "filename": "moc_0000_0089.csv",
        "companion_pattern": "moc_0000_0089.lbl",
        "role": "composition_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_0000_0089.csv",
    },
    {
        "dataset_id": "msl_chemcam_moc_0090_0179",
        "product_id": "MOC_0090_0179",
        "filename": "moc_0090_0179.csv",
        "companion_pattern": "moc_0090_0179.lbl",
        "role": "composition_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_0090_0179.csv",
    },
    {
        "dataset_id": "msl_chemcam_moc_1294_1417",
        "product_id": "MOC_1294_1417",
        "filename": "moc_1294_1417.csv",
        "companion_pattern": "moc_1294_1417.lbl",
        "role": "composition_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_1294_1417.csv",
    },
    {
        "dataset_id": "msl_chemin_cma_404470826min00790050104ch11503p1",
        "product_id": "CMA_404470826MIN00790050104CH11503P1",
        "filename": "cma_404470826min00790050104ch11503p1.csv",
        "companion_pattern": "cma_404470826min00790050104ch11503p1.lbl",
        "role": "composition_mineral_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_404470826min00790050104ch11503p1.csv",
    },
    {
        "dataset_id": "msl_chemin_cma_414856883min01960060000ch12240p1",
        "product_id": "CMA_414856883MIN01960060000CH12240P1",
        "filename": "cma_414856883min01960060000ch12240p1.csv",
        "companion_pattern": "cma_414856883min01960060000ch12240p1.lbl",
        "role": "composition_mineral_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_414856883min01960060000ch12240p1.csv",
    },
    {
        "dataset_id": "msl_chemin_cma_595174954min22270730550ch00111p1",
        "product_id": "CMA_595174954MIN22270730550CH00111P1",
        "filename": "cma_595174954min22270730550ch00111p1.csv",
        "companion_pattern": "cma_595174954min22270730550ch00111p1.lbl",
        "role": "composition_mineral_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_595174954min22270730550ch00111p1.csv",
    },
    {
        "dataset_id": "msl_chemin_cmb_476051894min08850450000ch00113p1",
        "product_id": "CMB_476051894MIN08850450000CH00113P1",
        "filename": "cmb_476051894min08850450000ch00113p1.csv",
        "companion_pattern": "cmb_476051894min08850450000ch00113p1.lbl",
        "role": "composition_mineral_table",
        "url": "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cmb_476051894min08850450000ch00113p1.csv",
    },
    {
        "dataset_id": "msl_crism_orbital_mineral_cube",
        "product_id": "CRISM_MINERAL_PRODUCT",
        "filename": "*crism*mineral*",
        "companion_pattern": None,
        "role": "orbital_mineral_cube",
        "declared_unavailable_default": True,
        "url": None,
    },
]


def _read_retrieval_sidecar(file_path: Path) -> Dict[str, Any]:
    """Read verified download sidecar if written by acquisition service; otherwise return 'unknown'."""
    sidecar = file_path.parent / f".{file_path.name}.retrieval.json"
    if sidecar.exists():
        try:
            obj = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and obj.get("retrieval_timestamp_utc"):
                return obj
        except Exception:
            pass
    return {"retrieval_timestamp_utc": "unknown"}


def _inspect_rights_metadata(file_path: Path) -> Tuple[RightsStatus, str]:
    """
    Determine explicit rights/license verification state strictly from artifact metadata.
    Never infers CC0 or public domain when rights tags are absent.
    """
    sfx = file_path.suffix.lower()
    if sfx == ".xml" and file_path.exists():
        try:
            meta = parse_pds4_table_delimited(file_path)
            if meta.get("rights_verified") and meta.get("rights_statements"):
                return RightsStatus.VERIFIED, "; ".join(meta["rights_statements"])
        except Exception:
            pass
    return (
        RightsStatus.NOT_VERIFIED,
        "License/rights metadata not embedded in local artifact; source bundle rights remain not_verified unless explicitly verified.",
    )


def _make_source_artifact_record(
    *,
    artifact_role: str,
    file_path: Optional[Path],
    dataset_id: Optional[str],
    product_id: Optional[str],
    source_url: Optional[str] = None,
    required: bool = True,
    rights_source_path: Optional[Path] = None,
) -> SourceArtifactRecord:
    """Build a verifiable dependency record for a raw data, label, format, or reference file."""
    if file_path is None or not file_path.exists():
        return SourceArtifactRecord(
            artifact_id=f"{artifact_role}:{file_path.name if file_path else product_id or 'missing'}",
            artifact_role=artifact_role,
            dataset_id=dataset_id,
            product_id=product_id,
            file_path=str(file_path) if file_path else "",
            required=required,
            present=False,
            verified=False,
            sha256_checksum=None,
            byte_size=None,
            retrieval_timestamp_utc="unknown",
            source_mtime_utc=None,
            source_url=source_url,
            license_status=RightsStatus.NOT_FOUND,
            rights_statement="Source artifact missing; rights cannot be evaluated.",
            failure_reason="Artifact missing on disk.",
        )

    st = file_path.stat()
    sc = _read_retrieval_sidecar(file_path)
    rights_status, rights_stmt = _inspect_rights_metadata(rights_source_path or file_path)
    return SourceArtifactRecord(
        artifact_id=f"{artifact_role}:{file_path.name}",
        artifact_role=artifact_role,
        dataset_id=dataset_id,
        product_id=product_id,
        file_path=str(file_path),
        required=required,
        present=True,
        verified=True,
        sha256_checksum=_sha256_file(file_path),
        byte_size=int(st.st_size),
        retrieval_timestamp_utc=str(sc.get("retrieval_timestamp_utc") or "unknown"),
        source_mtime_utc=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        source_url=source_url or sc.get("source_url"),
        license_status=rights_status,
        rights_statement=rights_stmt,
    )


class CompositionSpatialIndex:
    """Persistent, transaction-safe SQLite spatial index for verified planetary composition."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.rtree_enabled = self._init_schema()

    def _manifest_path(self) -> Path:
        if self.db_path.name == "composition_index.sqlite":
            return self.db_path.parent / "reproducibility_manifest.json"
        return self.db_path.parent / f"{self.db_path.stem}_reproducibility_manifest.json"

    def _connect_path(self, target_db: Path, wal_mode: bool = True) -> sqlite3.Connection:
        conn = sqlite3.connect(str(target_db), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;" if wal_mode else "PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _connect(self) -> sqlite3.Connection:
        return self._connect_path(self.db_path, wal_mode=True)

    def _init_schema_on(self, target_db: Path, wal_mode: bool = True) -> bool:
        with self._connect_path(target_db, wal_mode=wal_mode) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_generations (
                    generation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    generation_build_status TEXT NOT NULL DEFAULT 'partial',
                    discovery_scope TEXT NOT NULL DEFAULT 'static_seed_manifest',
                    created_at_utc TEXT NOT NULL,
                    source_manifest_checksum TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    located_count INTEGER NOT NULL DEFAULT 0,
                    unlocated_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    expected_products_count INTEGER NOT NULL DEFAULT 0,
                    crism_status TEXT NOT NULL DEFAULT 'unavailable_no_validated_mineral_cube',
                    notes_json TEXT NOT NULL DEFAULT '[]',
                    missing_expected_json TEXT NOT NULL DEFAULT '[]',
                    product_audit_json TEXT NOT NULL DEFAULT '[]',
                    dependency_artifacts_json TEXT NOT NULL DEFAULT '[]',
                    rights_summary_json TEXT NOT NULL DEFAULT '{}',
                    retrieval_metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS ingested_products (
                    generation_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    sha256_checksum TEXT NOT NULL,
                    record_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    ingested_at_utc TEXT NOT NULL,
                    manifest_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (generation_id, product_id)
                );

                CREATE TABLE IF NOT EXISTS composition_evidence (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    source_dataset_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    instrument_id TEXT NOT NULL,
                    target_name TEXT,
                    sol INTEGER,
                    canonical_species_id TEXT NOT NULL,
                    species_category TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    evidence_status TEXT NOT NULL,
                    raw_value REAL,
                    raw_unit TEXT,
                    normalized_value REAL,
                    normalized_unit TEXT,
                    uncertainty_value REAL,
                    quality_flag TEXT,
                    location_verified INTEGER NOT NULL DEFAULT 0,
                    latitude REAL,
                    longitude_east REAL,
                    min_lat REAL,
                    max_lat REAL,
                    min_lon_east REAL,
                    max_lon_east REAL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ev_gen_species_loc
                    ON composition_evidence (generation_id, canonical_species_id, location_verified);
                CREATE INDEX IF NOT EXISTS idx_ev_gen_inst
                    ON composition_evidence (generation_id, instrument_id);
                CREATE INDEX IF NOT EXISTS idx_ev_gen_target
                    ON composition_evidence (generation_id, target_name);
                CREATE INDEX IF NOT EXISTS idx_ev_gen_bbox
                    ON composition_evidence (generation_id, location_verified, min_lat, max_lat, min_lon_east, max_lon_east);

                CREATE TABLE IF NOT EXISTS rejected_records (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id TEXT NOT NULL,
                    rejection_id TEXT NOT NULL,
                    source_dataset_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    instrument_id TEXT NOT NULL,
                    rejection_stage INTEGER NOT NULL,
                    rejection_code TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rej_gen
                    ON rejected_records (generation_id, rejection_code);
                """
            )
            rtree_ok = False
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS evidence_rtree USING rtree(
                        row_id,
                        min_lon, max_lon,
                        min_lat, max_lat
                    );
                    """
                )
                rtree_ok = True
            except sqlite3.OperationalError:
                rtree_ok = False
            conn.commit()
            # Graceful migration for pre-existing SQLite databases
            prod_cols = {r[1] for r in conn.execute("PRAGMA table_info(ingested_products)").fetchall()}
            if "manifest_json" not in prod_cols:
                conn.execute("ALTER TABLE ingested_products ADD COLUMN manifest_json TEXT NOT NULL DEFAULT '{}'")
            gen_cols = {r[1] for r in conn.execute("PRAGMA table_info(index_generations)").fetchall()}
            migrations = {
                "generation_build_status": "TEXT NOT NULL DEFAULT 'partial'",
                "discovery_scope": "TEXT NOT NULL DEFAULT 'static_seed_manifest'",
                "expected_products_count": "INTEGER NOT NULL DEFAULT 0",
                "missing_expected_json": "TEXT NOT NULL DEFAULT '[]'",
                "product_audit_json": "TEXT NOT NULL DEFAULT '[]'",
                "dependency_artifacts_json": "TEXT NOT NULL DEFAULT '[]'",
                "rights_summary_json": "TEXT NOT NULL DEFAULT '{}'",
                "retrieval_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            for col_name, col_ddl in migrations.items():
                if col_name not in gen_cols:
                    conn.execute(f"ALTER TABLE index_generations ADD COLUMN {col_name} {col_ddl}")
            conn.commit()
            return rtree_ok

    def _init_schema(self) -> bool:
        return self._init_schema_on(self.db_path, wal_mode=True)

    def get_active_generation(self) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM index_generations WHERE status = 'active' ORDER BY created_at_utc DESC LIMIT 1"
            ).fetchone()

    def _validate_staged_generation(
        self,
        staging_db: Path,
        staging_manifest: Path,
        expected_gen_id: str,
        require_source_files: bool = True,
    ) -> None:
        """
        Verify a staged generation DB and staged manifest completely before atomic cutover.
        Raises RuntimeError on any integrity, count, checksum, or schema violation.
        """
        if not staging_db.exists() or not staging_manifest.exists():
            raise RuntimeError("Staging database or staging manifest missing before cutover.")
        try:
            manifest_obj = json.loads(staging_manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Staging manifest JSON is unreadable: {exc}") from exc

        req_keys = {
            "manifest_format_version",
            "generation_id",
            "source_manifest_checksum",
            "generation_build_status",
            "products",
            "dependency_artifacts",
        }
        missing_keys = req_keys - set(manifest_obj.keys())
        if missing_keys:
            raise RuntimeError(f"Staging manifest missing required keys: {sorted(missing_keys)}")
        if manifest_obj.get("generation_id") != expected_gen_id:
            raise RuntimeError(
                f"Manifest generation_id '{manifest_obj.get('generation_id')}' != '{expected_gen_id}'."
            )

        with self._connect_path(staging_db, wal_mode=False) as conn:
            gen_row = conn.execute(
                "SELECT * FROM index_generations WHERE generation_id = ? AND status = 'active'",
                (expected_gen_id,),
            ).fetchone()
            if gen_row is None:
                raise RuntimeError(f"Staging DB lacks active generation '{expected_gen_id}'.")
            if gen_row["source_manifest_checksum"] != manifest_obj["source_manifest_checksum"]:
                raise RuntimeError("Staging DB manifest checksum disagrees with staging manifest JSON.")

            ev_cnt, loc_cnt = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN location_verified = 1 THEN 1 ELSE 0 END) FROM composition_evidence WHERE generation_id = ?",
                (expected_gen_id,),
            ).fetchone()
            ev_cnt = int(ev_cnt or 0)
            loc_cnt = int(loc_cnt or 0)
            rej_cnt = int(
                conn.execute(
                    "SELECT COUNT(*) FROM rejected_records WHERE generation_id = ?", (expected_gen_id,)
                ).fetchone()[0]
            )
            if ev_cnt != int(gen_row["evidence_count"]) or loc_cnt != int(gen_row["located_count"]):
                raise RuntimeError("Staging DB evidence counts disagree with index_generations header.")
            if rej_cnt != int(gen_row["rejected_count"]):
                raise RuntimeError("Staging DB rejected record count disagrees with index_generations header.")

            # Verify deterministic IDs across staged evidence rows
            for row in conn.execute(
                "SELECT payload_json FROM composition_evidence WHERE generation_id = ?", (expected_gen_id,)
            ):
                ev_obj = CompositionEvidence.model_validate_json(row[0])
                exp_id = compute_deterministic_evidence_id(ev_obj)
                if ev_obj.evidence_id != exp_id:
                    raise RuntimeError(
                        f"Pre-cutover deterministic ID mismatch for {ev_obj.source_record_ref}: "
                        f"{ev_obj.evidence_id} != {exp_id}."
                    )

        if require_source_files:
            for dep in manifest_obj.get("dependency_artifacts", []):
                if not dep.get("present") or not dep.get("file_path"):
                    if dep.get("required", True):
                        raise RuntimeError(f"Required dependency missing during staging verification: {dep.get('artifact_id')}")
                    continue
                dp = Path(dep["file_path"])
                if not dp.exists():
                    raise RuntimeError(f"Dependency vanished before cutover: {dp}")
                if dep.get("sha256_checksum") and _sha256_file(dp) != dep["sha256_checksum"]:
                    raise RuntimeError(f"Dependency checksum changed before cutover: {dp.name}")

    def publish_generation(
        self,
        evidence_records: List[CompositionEvidence],
        rejected_records: List[RejectionRecord],
        product_manifests: Optional[List[Dict[str, Any]]] = None,
        dependency_artifacts: Optional[List[Dict[str, Any]]] = None,
        product_audit: Optional[List[Dict[str, Any]]] = None,
        generation_build_status: Optional[GenerationBuildStatus] = None,
        discovery_scope: str = "static_seed_manifest",
        expected_products_count: int = 0,
        missing_expected_products: Optional[List[str]] = None,
        rights_summary: Optional[Dict[str, Any]] = None,
        retrieval_metadata: Optional[Dict[str, Any]] = None,
        crism_status: str = "unavailable_no_validated_mineral_cube",
        notes: Optional[List[str]] = None,
        generation_id: Optional[str] = None,
        simulate_failure_before_cutover: bool = False,
    ) -> CompositionIndexStatus:
        """
        Build a candidate index generation inside an isolated staging SQLite database,
        verify all counts, deterministic IDs, checksums, and manifest integrity, and
        atomically replace the active database & reproducibility manifest only if every
        check passes. On any failure, preserves the previous active generation untouched.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        manifests = sorted(
            product_manifests or [],
            key=lambda m: (str(m.get("dataset_id", "")), str(m.get("product_id", ""))),
        )
        deps = sorted(
            dependency_artifacts or [],
            key=lambda d: (str(d.get("artifact_role", "")), str(d.get("file_path", ""))),
        )
        dep_digest_items = [
            (d.get("artifact_id", ""), d.get("sha256_checksum", "")) for d in deps
        ] + [
            (m.get("product_id", ""), m.get("sha256_checksum", "")) for m in manifests
        ]
        manifest_digest = hashlib.sha256(
            json.dumps(dep_digest_items, sort_keys=True).encode("utf-8")
        ).hexdigest()
        ev_digest = hashlib.sha256(
            "|".join(e.evidence_id for e in sorted(evidence_records, key=lambda x: x.evidence_id)).encode("utf-8")
        ).hexdigest()
        gen_id = generation_id or f"gen_{hashlib.sha256(f'{manifest_digest}|{ev_digest}|{len(rejected_records)}'.encode()).hexdigest()[:12]}"

        located_count = sum(1 for e in evidence_records if e.location_verified)
        unlocated_count = len(evidence_records) - located_count
        build_status = generation_build_status or (
            GenerationBuildStatus.COMPLETE_WITH_DECLARED_UNAVAILABLE_SOURCES
            if len(evidence_records) > 0 and not (missing_expected_products or [])
            else (GenerationBuildStatus.PARTIAL if len(evidence_records) > 0 else GenerationBuildStatus.FAILED)
        )

        staging_db = self.db_path.parent / f".{self.db_path.name}.staging.sqlite"
        manifest_path = self._manifest_path()
        staging_manifest = manifest_path.parent / f".{manifest_path.name}.staging.json"
        for leftover in (
            staging_db,
            Path(f"{staging_db}-wal"),
            Path(f"{staging_db}-shm"),
            staging_manifest,
        ):
            if leftover.exists():
                leftover.unlink()

        try:
            staging_rtree = self._init_schema_on(staging_db, wal_mode=False)
            with self._connect_path(staging_db, wal_mode=False) as sconn:
                sconn.execute("BEGIN IMMEDIATE;")
                sconn.execute(
                    """
                    INSERT INTO index_generations (
                        generation_id, status, generation_build_status, discovery_scope,
                        created_at_utc, source_manifest_checksum,
                        evidence_count, located_count, unlocated_count, rejected_count,
                        expected_products_count, crism_status, notes_json,
                        missing_expected_json, product_audit_json, dependency_artifacts_json,
                        rights_summary_json, retrieval_metadata_json
                    ) VALUES (?, 'building', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gen_id,
                        build_status.value,
                        discovery_scope,
                        now_utc,
                        manifest_digest,
                        len(evidence_records),
                        located_count,
                        unlocated_count,
                        len(rejected_records),
                        int(expected_products_count),
                        crism_status,
                        json.dumps(notes or []),
                        json.dumps(missing_expected_products or []),
                        json.dumps(product_audit or []),
                        json.dumps(deps),
                        json.dumps(rights_summary or {}),
                        json.dumps(retrieval_metadata or {}),
                    ),
                )

                for m in manifests:
                    sconn.execute(
                        """
                        INSERT OR REPLACE INTO ingested_products (
                            generation_id, dataset_id, product_id, file_path,
                            sha256_checksum, record_count, rejected_count, ingested_at_utc, manifest_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            gen_id,
                            m["dataset_id"],
                            m["product_id"],
                            m["file_path"],
                            m["sha256_checksum"],
                            int(m.get("record_count", 0)),
                            int(m.get("rejected_count", 0)),
                            now_utc,
                            json.dumps(m, sort_keys=True),
                        ),
                    )

                for ev in evidence_records:
                    ev_copy = ev.model_copy(update={"generation_id": gen_id})
                    lon_360 = normalize_longitude_360(ev_copy.longitude_east) if ev_copy.longitude_east is not None else None
                    min_lon = normalize_longitude_360(ev_copy.min_lon_east) if ev_copy.min_lon_east is not None else lon_360
                    max_lon = normalize_longitude_360(ev_copy.max_lon_east) if ev_copy.max_lon_east is not None else lon_360
                    cur = sconn.execute(
                        """
                        INSERT INTO composition_evidence (
                            generation_id, evidence_id, source_dataset_id, product_id,
                            instrument_id, target_name, sol, canonical_species_id,
                            species_category, evidence_type, evidence_status,
                            raw_value, raw_unit, normalized_value, normalized_unit,
                            uncertainty_value, quality_flag, location_verified,
                            latitude, longitude_east, min_lat, max_lat,
                            min_lon_east, max_lon_east, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            gen_id,
                            ev_copy.evidence_id,
                            ev_copy.source_dataset_id,
                            ev_copy.product_id,
                            ev_copy.instrument_id,
                            ev_copy.target_name,
                            ev_copy.sol,
                            ev_copy.canonical_species_id,
                            ev_copy.species_category.value,
                            ev_copy.evidence_type.value,
                            ev_copy.evidence_status.value,
                            ev_copy.raw_value,
                            ev_copy.raw_unit,
                            ev_copy.normalized_value,
                            ev_copy.normalized_unit,
                            ev_copy.uncertainty_value,
                            ev_copy.quality_flag,
                            1 if ev_copy.location_verified else 0,
                            ev_copy.latitude,
                            lon_360,
                            ev_copy.min_lat if ev_copy.min_lat is not None else ev_copy.latitude,
                            ev_copy.max_lat if ev_copy.max_lat is not None else ev_copy.latitude,
                            min_lon,
                            max_lon,
                            ev_copy.model_dump_json(),
                        ),
                    )
                    row_id = cur.lastrowid
                    if (
                        staging_rtree
                        and ev_copy.location_verified
                        and ev_copy.latitude is not None
                        and min_lon is not None
                        and max_lon is not None
                    ):
                        mn_lat = ev_copy.min_lat if ev_copy.min_lat is not None else ev_copy.latitude
                        mx_lat = ev_copy.max_lat if ev_copy.max_lat is not None else ev_copy.latitude
                        if min_lon <= max_lon:
                            sconn.execute(
                                "INSERT INTO evidence_rtree (row_id, min_lon, max_lon, min_lat, max_lat) VALUES (?, ?, ?, ?, ?)",
                                (row_id, min_lon, max_lon, mn_lat, mx_lat),
                            )

                for rej in rejected_records:
                    sconn.execute(
                        """
                        INSERT INTO rejected_records (
                            generation_id, rejection_id, source_dataset_id, product_id,
                            instrument_id, rejection_stage, rejection_code, reason, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            gen_id,
                            rej.rejection_id,
                            rej.source_dataset_id,
                            rej.product_id,
                            rej.instrument_id,
                            rej.rejection_stage,
                            rej.rejection_code,
                            rej.reason,
                            rej.model_dump_json(),
                        ),
                    )

                sconn.execute("UPDATE index_generations SET status = 'active' WHERE generation_id = ?", (gen_id,))
                sconn.commit()

            repro_payload = {
                "manifest_format_version": "reproducibility_manifest_v2",
                "generation_id": gen_id,
                "generation_build_status": build_status.value,
                "discovery_scope": discovery_scope,
                "built_at_utc": now_utc,
                "source_manifest_checksum": manifest_digest,
                "sqlite_path": str(self.db_path),
                "determinism_version": EVIDENCE_ID_DETERMINISM_VERSION,
                "validation_pipeline_version": "12_stage_v3",
                "ranking_config_id": DEFAULT_HEURISTIC_RANKING_CONFIG.ranking_config_id,
                "ranking_config_version": DEFAULT_HEURISTIC_RANKING_CONFIG.ranking_config_version,
                "total_validated_evidence": len(evidence_records),
                "located_evidence_count": located_count,
                "unlocated_evidence_count": unlocated_count,
                "rejected_record_count": len(rejected_records),
                "expected_products_count": int(expected_products_count),
                "missing_expected_products": missing_expected_products or [],
                "crism_status": crism_status,
                "rights_summary": rights_summary or {},
                "retrieval_metadata": retrieval_metadata or {},
                "products": manifests,
                "dependency_artifacts": deps,
                "product_audit": product_audit or [],
                "notes": notes or [],
            }
            staging_manifest.write_text(json.dumps(repro_payload, indent=2), encoding="utf-8")

            # Pre-cutover strict verification in isolated staging area
            self._validate_staged_generation(
                staging_db,
                staging_manifest,
                expected_gen_id=gen_id,
                require_source_files=bool(manifests or deps),
            )
            if simulate_failure_before_cutover:
                raise RuntimeError("Simulated pre-cutover failure: aborting atomic cutover.")

            # Switch existing DB out of WAL mode / clean stray WAL sidecars before atomic os.replace
            for stale_wal in (Path(f"{self.db_path}-wal"), Path(f"{self.db_path}-shm")):
                if stale_wal.exists():
                    try:
                        with self._connect_path(self.db_path, wal_mode=False) as pconn:
                            pconn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    except Exception:
                        pass
                    if stale_wal.exists():
                        stale_wal.unlink()

            os.replace(staging_db, self.db_path)
            os.replace(staging_manifest, manifest_path)
        finally:
            for leftover in (
                staging_db,
                Path(f"{staging_db}-wal"),
                Path(f"{staging_db}-shm"),
                staging_manifest,
            ):
                if leftover.exists():
                    try:
                        leftover.unlink()
                    except OSError:
                        pass

        self.rtree_enabled = self._init_schema()
        return self.get_status()

    @staticmethod
    def _build_product_manifest(
        *,
        dataset_id: str,
        product_id: str,
        file_path: Path,
        source_url: str,
        label_path: Optional[Path],
        schema_version: str,
        parser_id: str,
        parser_version: str,
        coord_method: str,
        record_count: int,
        rejected_count: int,
        companion_paths: Optional[List[Path]] = None,
    ) -> Dict[str, Any]:
        st = file_path.stat()
        sc = _read_retrieval_sidecar(file_path)
        rights_src = label_path if (label_path and label_path.suffix.lower() == ".xml") else file_path
        license_status, rights_stmt = _inspect_rights_metadata(rights_src)
        companion_entries = []
        for cp in companion_paths or []:
            if cp and cp.exists():
                cst = cp.stat()
                csc = _read_retrieval_sidecar(cp)
                companion_entries.append(
                    {
                        "file_name": cp.name,
                        "file_path": str(cp),
                        "sha256_checksum": _sha256_file(cp),
                        "byte_size": int(cst.st_size),
                        "retrieval_timestamp_utc": str(csc.get("retrieval_timestamp_utc") or "unknown"),
                        "source_mtime_utc": datetime.fromtimestamp(cst.st_mtime, tz=timezone.utc).isoformat(),
                    }
                )
        return {
            "dataset_id": dataset_id,
            "product_id": product_id,
            "source_url": source_url or sc.get("source_url"),
            "file_path": str(file_path),
            "byte_size": int(st.st_size),
            "retrieval_timestamp_utc": str(sc.get("retrieval_timestamp_utc") or "unknown"),
            "source_mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "sha256_checksum": _sha256_file(file_path),
            "license_status": license_status.value,
            "rights_statement": rights_stmt,
            "label_path": str(label_path) if label_path else None,
            "label_sha256_checksum": _sha256_file(label_path) if (label_path and label_path.exists()) else None,
            "companion_dependencies": companion_entries,
            "schema_version": schema_version,
            "parser_id": parser_id,
            "parser_version": parser_version,
            "validation_pipeline_version": "12_stage_v3",
            "determinism_version": EVIDENCE_ID_DETERMINISM_VERSION,
            "coordinate_association_method": coord_method,
            "record_count": int(record_count),
            "rejected_count": int(rejected_count),
        }

    def rebuild_from_raw_directory(
        self,
        raw_dir: Path,
        processed_dir: Path,
        declared_unavailable_sources: Optional[List[str]] = None,
        strict_mode: bool = False,
        simulate_failure_before_cutover: bool = False,
    ) -> CompositionIndexStatus:
        """
        Discover and parse verified NASA PDS raw artifacts inside raw_dir, track
        expected-vs-discovered product completeness and source dependency artifacts
        (.LBL/.XML/.FMT/waypoints), run 12-stage validation, and atomically publish
        via staging DB cutover. If build fails, preserves any existing active DB.
        """
        def _glob_ci(pattern: str) -> List[Path]:
            if not raw_dir.exists():
                return []
            pat = pattern.lower()
            return sorted(
                p for p in raw_dir.iterdir() if p.is_file() and fnmatch.fnmatchcase(p.name.lower(), pat)
            )

        def _find_companion(base_path: Path, suffixes: Tuple[str, ...]) -> Optional[Path]:
            for sfx in suffixes:
                cand = base_path.with_suffix(sfx)
                if cand.exists():
                    return cand
            return None

        declared_unavail = {s.lower() for s in (declared_unavailable_sources or ["crism"])}
        coord_svc = CoordinateAssociationService()
        wp_candidates = _glob_ci("*waypoints*.json")
        notes: List[str] = []
        manifests: List[Dict[str, Any]] = []
        dep_records: List[Dict[str, Any]] = []
        audit_by_file: Dict[str, ProductAuditEntry] = {}

        wp_path: Optional[Path] = wp_candidates[0] if wp_candidates else None
        if wp_path:
            wp_count = coord_svc.load_waypoints_geojson(wp_path)
            notes.append(f"Loaded {wp_count} JPL MSL traverse waypoints from {wp_path.name}.")
            dep_records.append(
                _make_source_artifact_record(
                    artifact_role="localization_reference",
                    file_path=wp_path,
                    dataset_id="jpl_msl_traverse_waypoints",
                    product_id=wp_path.stem.upper(),
                    source_url="https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json",
                    required=True,
                ).model_dump()
            )
            manifests.append(
                self._build_product_manifest(
                    dataset_id="jpl_msl_traverse_waypoints",
                    product_id=wp_path.stem.upper(),
                    file_path=wp_path,
                    source_url="https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json",
                    label_path=None,
                    schema_version="geojson_feature_collection",
                    parser_id="coordinate_association_waypoints",
                    parser_version="2.0.0",
                    coord_method="rmc_site_drive_lookup",
                    record_count=wp_count,
                    rejected_count=0,
                )
            )
            audit_by_file[wp_path.name.lower()] = ProductAuditEntry(
                dataset_id="jpl_msl_traverse_waypoints",
                product_id=wp_path.stem.upper(),
                expected_artifact_name=wp_path.name,
                discovery_scope="static_seed_manifest",
                present_locally=True,
                build_status="ingested",
                accepted_record_count=wp_count,
                rejected_record_count=0,
            )
        else:
            notes.append("No JPL MSL_waypoints.json file in raw_dir; RMC coordinate joins will mark records unlocated.")

        evidence_all: List[CompositionEvidence] = []
        rejected_all: List[RejectionRecord] = []
        fatal_errors: List[str] = []

        def _record_product_failure(dataset_id: str, csv_path: Path, dep_names: List[str], exc: Exception) -> None:
            err_msg = str(exc)
            notes.append(f"Product '{csv_path.name}' failed schema/ingestion validation: {err_msg}")
            fatal_errors.append(f"{csv_path.name}: {err_msg}")
            rkey = f"{dataset_id}|{csv_path.stem.upper()}|PRODUCT_VALIDATION_FAILED|{err_msg}"
            rejected_all.append(
                RejectionRecord(
                    rejection_id=hashlib.sha256(rkey.encode("utf-8")).hexdigest()[:20],
                    source_dataset_id=dataset_id,
                    product_id=csv_path.stem.upper(),
                    source_record_ref=csv_path.name,
                    instrument_id=dataset_id.split("_")[1].upper() if "_" in dataset_id else "UNKNOWN",
                    rejection_stage=0,
                    rejection_code="PRODUCT_SCHEMA_VALIDATION_FAILED",
                    reason=err_msg,
                    raw_payload={"file": csv_path.name, "dependencies": dep_names},
                )
            )
            audit_by_file[csv_path.name.lower()] = ProductAuditEntry(
                dataset_id=dataset_id,
                product_id=csv_path.stem.upper(),
                expected_artifact_name=csv_path.name,
                discovery_scope="local_raw_directory_scan",
                present_locally=True,
                build_status="failed",
                accepted_record_count=0,
                rejected_record_count=1,
                companion_dependencies=dep_names,
                failure_reason=err_msg,
            )

        if raw_dir.exists():
            # 1. APXS Supplement CSVs (PDS4 XML required)
            apxs_files = sorted({p for p in _glob_ci("*2021je007171r*.csv") + _glob_ci("*apxs*.csv")})
            for csv_path in apxs_files:
                xml_lbl = _find_companion(csv_path, (".xml", ".XML"))
                url = "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/ds01_2021je007171r.csv"
                xml_url = "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/ds01_2021je007171r.xml"
                try:
                    acc, rej = ApxsEvidenceAdapter.adapt_csv(
                        csv_path,
                        source_dataset_id="msl_apxs_supplement_sols_0_3076",
                        product_id=csv_path.stem.upper(),
                        provenance_url=url,
                        label_path=xml_lbl,
                    )
                except Exception as exc:
                    _record_product_failure(
                        "msl_apxs_supplement_sols_0_3076",
                        csv_path,
                        [xml_lbl.name] if xml_lbl else [],
                        exc,
                    )
                    continue

                evidence_all.extend(acc)
                rejected_all.extend(rej)
                dep_records.append(
                    _make_source_artifact_record(
                        artifact_role="primary_data",
                        file_path=csv_path,
                        dataset_id="msl_apxs_supplement_sols_0_3076",
                        product_id=csv_path.stem.upper(),
                        source_url=url,
                        rights_source_path=xml_lbl or csv_path,
                    ).model_dump()
                )
                dep_records.append(
                    _make_source_artifact_record(
                        artifact_role="pds4_xml_label",
                        file_path=xml_lbl,
                        dataset_id="msl_apxs_supplement_sols_0_3076",
                        product_id=csv_path.stem.upper(),
                        source_url=xml_url,
                        rights_source_path=xml_lbl,
                    ).model_dump()
                )
                manifests.append(
                    self._build_product_manifest(
                        dataset_id="msl_apxs_supplement_sols_0_3076",
                        product_id=csv_path.stem.upper(),
                        file_path=csv_path,
                        source_url=url,
                        label_path=xml_lbl,
                        schema_version=acc[0].schema_version if acc and acc[0].schema_version else "pds4_xml",
                        parser_id="apxs_pds4_schema_parser",
                        parser_version="3.0.0",
                        coord_method="gale_eqc_target_pyproj",
                        record_count=len(acc),
                        rejected_count=len(rej),
                        companion_paths=[xml_lbl] if xml_lbl else [],
                    )
                )
                audit_by_file[csv_path.name.lower()] = ProductAuditEntry(
                    dataset_id="msl_apxs_supplement_sols_0_3076",
                    product_id=csv_path.stem.upper(),
                    expected_artifact_name=csv_path.name,
                    discovery_scope="static_seed_manifest",
                    present_locally=True,
                    build_status="ingested",
                    accepted_record_count=len(acc),
                    rejected_record_count=len(rej),
                    companion_dependencies=[xml_lbl.name] if xml_lbl else [],
                )

            # 2. ChemCam MOC Tables
            for moc_csv in _glob_ci("moc_*.csv"):
                lbl = _find_companion(moc_csv, (".lbl", ".LBL"))
                ds_id = f"msl_chemcam_{moc_csv.stem.lower()}"
                url = f"https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/{moc_csv.name}"
                lbl_url = url.rsplit(".", 1)[0] + ".lbl"
                try:
                    acc, rej = ChemCamEvidenceAdapter.adapt_moc_csv(
                        moc_csv,
                        label_path=lbl,
                        source_dataset_id=ds_id,
                        coord_service=coord_svc,
                        provenance_url=url,
                    )
                except Exception as exc:
                    _record_product_failure(ds_id, moc_csv, [lbl.name] if lbl else [], exc)
                    continue

                evidence_all.extend(acc)
                rejected_all.extend(rej)
                dep_records.append(
                    _make_source_artifact_record(
                        artifact_role="primary_data",
                        file_path=moc_csv,
                        dataset_id=ds_id,
                        product_id=moc_csv.stem.upper(),
                        source_url=url,
                    ).model_dump()
                )
                if lbl:
                    dep_records.append(
                        _make_source_artifact_record(
                            artifact_role="pds3_label",
                            file_path=lbl,
                            dataset_id=ds_id,
                            product_id=moc_csv.stem.upper(),
                            source_url=lbl_url,
                        ).model_dump()
                    )
                comp_list = [p for p in (lbl, wp_path) if p is not None]
                manifests.append(
                    self._build_product_manifest(
                        dataset_id=ds_id,
                        product_id=moc_csv.stem.upper(),
                        file_path=moc_csv,
                        source_url=url,
                        label_path=lbl,
                        schema_version=acc[0].schema_version if acc and acc[0].schema_version else "pds3_moc",
                        parser_id="chemcam_moc_schema_parser",
                        parser_version="2.1.0",
                        coord_method="rmc_site_drive_rover_station",
                        record_count=len(acc),
                        rejected_count=len(rej),
                        companion_paths=comp_list,
                    )
                )
                audit_by_file[moc_csv.name.lower()] = ProductAuditEntry(
                    dataset_id=ds_id,
                    product_id=moc_csv.stem.upper(),
                    expected_artifact_name=moc_csv.name,
                    discovery_scope="static_seed_manifest",
                    present_locally=True,
                    build_status="ingested",
                    accepted_record_count=len(acc),
                    rejected_record_count=len(rej),
                    companion_dependencies=[p.name for p in comp_list],
                )

            # 3. CheMin Mineral RDR5 Tables
            for cm_csv in _glob_ci("cm*min*.csv"):
                lbl = _find_companion(cm_csv, (".lbl", ".LBL"))
                ds_id = f"msl_chemin_{cm_csv.stem.lower()}"
                url = f"https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/{cm_csv.name}"
                lbl_url = url.rsplit(".", 1)[0] + ".lbl"
                try:
                    acc, rej = CheMinEvidenceAdapter.adapt_rdr5_csv(
                        cm_csv,
                        label_path=lbl,
                        source_dataset_id=ds_id,
                        coord_service=coord_svc,
                        extra_structure_dirs=[raw_dir],
                        provenance_url=url,
                    )
                except Exception as exc:
                    _record_product_failure(ds_id, cm_csv, [lbl.name] if lbl else [], exc)
                    continue

                evidence_all.extend(acc)
                rejected_all.extend(rej)
                resolved_fmts: List[Path] = []
                if lbl and lbl.exists():
                    meta = extract_pds3_metadata(lbl)
                    sfile = meta.get("structure_file")
                    if sfile:
                        for cand_n in (sfile, str(sfile).lower(), str(sfile).upper()):
                            cand_p = raw_dir / cand_n
                            if cand_p.exists():
                                resolved_fmts.append(cand_p)
                                break
                dep_records.append(
                    _make_source_artifact_record(
                        artifact_role="primary_data",
                        file_path=cm_csv,
                        dataset_id=ds_id,
                        product_id=cm_csv.stem.upper(),
                        source_url=url,
                    ).model_dump()
                )
                dep_records.append(
                    _make_source_artifact_record(
                        artifact_role="pds3_label",
                        file_path=lbl,
                        dataset_id=ds_id,
                        product_id=cm_csv.stem.upper(),
                        source_url=lbl_url,
                    ).model_dump()
                )
                for fp in resolved_fmts:
                    dep_records.append(
                        _make_source_artifact_record(
                            artifact_role="pds3_format_schema",
                            file_path=fp,
                            dataset_id=ds_id,
                            product_id=cm_csv.stem.upper(),
                            source_url="https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/label/chemin_min.fmt",
                        ).model_dump()
                    )
                comp_list = [p for p in ([lbl] + resolved_fmts + [wp_path]) if p is not None]
                manifests.append(
                    self._build_product_manifest(
                        dataset_id=ds_id,
                        product_id=cm_csv.stem.upper(),
                        file_path=cm_csv,
                        source_url=url,
                        label_path=lbl,
                        schema_version=acc[0].schema_version if acc and acc[0].schema_version else "pds3_chemin_fmt",
                        parser_id="chemin_rdr5_schema_parser",
                        parser_version="3.0.0",
                        coord_method="rmc_site_drive_rover_station",
                        record_count=len(acc),
                        rejected_count=len(rej),
                        companion_paths=comp_list,
                    )
                )
                audit_by_file[cm_csv.name.lower()] = ProductAuditEntry(
                    dataset_id=ds_id,
                    product_id=cm_csv.stem.upper(),
                    expected_artifact_name=cm_csv.name,
                    discovery_scope="static_seed_manifest",
                    present_locally=True,
                    build_status="ingested",
                    accepted_record_count=len(acc),
                    rejected_record_count=len(rej),
                    companion_dependencies=[p.name for p in comp_list],
                )

            # 4. Audit non-compositional raw ChemCam PSV & REMS files into rejected_records
            for psv_tab in _glob_ci("*psv*.tab"):
                lbl = _find_companion(psv_tab, (".lbl", ".LBL"))
                rej = ChemCamEvidenceAdapter.audit_raw_psv_as_non_compositional(
                    psv_tab,
                    label_path=lbl,
                )
                rejected_all.extend(rej)

            for rems_tab in _glob_ci("rme_*.tab"):
                rej = EnvironmentalExclusionAdapter.audit_non_composition_file(rems_tab)
                rejected_all.extend(rej)

        crism_status, _ = CrismEvidenceAdapter.check_availability(raw_dir, processed_dir)

        # Deduplicate dependency artifact records by (role, file_path)
        seen_deps: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for d in dep_records:
            seen_deps[(str(d.get("artifact_role")), str(d.get("file_path")))] = d
        unique_deps = list(seen_deps.values())

        # Compute expected-vs-discovered product audit
        product_audit: List[Dict[str, Any]] = []
        missing_expected: List[str] = []
        declared_unavail_used = False
        for exp in EXPECTED_COMPOSITION_PRODUCTS:
            fname = exp["filename"]
            if exp.get("declared_unavailable_default"):
                if crism_status == "unavailable_no_validated_mineral_cube":
                    if (
                        exp["dataset_id"].lower() in declared_unavail
                        or exp["product_id"].lower() in declared_unavail
                        or any("crism" in str(x).lower() for x in declared_unavail)
                    ):
                        declared_unavail_used = True
                        product_audit.append(
                            ProductAuditEntry(
                                dataset_id=exp["dataset_id"],
                                product_id=exp["product_id"],
                                expected_artifact_name=fname,
                                discovery_scope="static_seed_manifest",
                                present_locally=False,
                                build_status="declared_unavailable",
                                failure_reason=crism_status,
                            ).model_dump()
                        )
                    else:
                        missing_expected.append(exp["product_id"])
                        product_audit.append(
                            ProductAuditEntry(
                                dataset_id=exp["dataset_id"],
                                product_id=exp["product_id"],
                                expected_artifact_name=fname,
                                discovery_scope="static_seed_manifest",
                                present_locally=False,
                                build_status="missing_expected",
                                failure_reason=crism_status,
                            ).model_dump()
                        )
                continue

            matched = audit_by_file.get(fname.lower())
            if matched is not None:
                product_audit.append(matched.model_dump())
            else:
                missing_expected.append(fname)
                product_audit.append(
                    ProductAuditEntry(
                        dataset_id=exp["dataset_id"],
                        product_id=exp["product_id"],
                        expected_artifact_name=fname,
                        discovery_scope="static_seed_manifest",
                        present_locally=False,
                        build_status="missing_expected",
                        failure_reason=f"Expected product '{fname}' absent from raw_dir.",
                    ).model_dump()
                )

        # Preserve extra local files discovered outside static seed list
        known_lower = {e["filename"].lower() for e in EXPECTED_COMPOSITION_PRODUCTS}
        for k, entry in sorted(audit_by_file.items()):
            if k not in known_lower:
                entry.discovery_scope = "local_raw_directory_scan"
                product_audit.append(entry.model_dump())

        # Determine exact generation completeness status
        if (strict_mode and (fatal_errors or missing_expected)) or len(evidence_all) == 0:
            fail_notes = list(notes)
            if not evidence_all:
                fail_notes.append("Build aborted: zero validated evidence records produced.")
            return CompositionIndexStatus(
                index_available=False,
                integrity_status=IntegrityStatus.UNAVAILABLE,
                generation_build_status=GenerationBuildStatus.FAILED,
                expected_products_count=len(EXPECTED_COMPOSITION_PRODUCTS),
                missing_expected_products=missing_expected,
                discovery_scope="static_seed_manifest",
                product_audit=product_audit,
                dependency_artifacts=unique_deps,
                rejected_record_count=len(rejected_all),
                crism_status=crism_status,
                sqlite_path=str(self.db_path),
                notes=fail_notes,
            )

        if fatal_errors or missing_expected:
            build_status = GenerationBuildStatus.PARTIAL
        elif declared_unavail_used:
            build_status = GenerationBuildStatus.COMPLETE_WITH_DECLARED_UNAVAILABLE_SOURCES
        else:
            build_status = GenerationBuildStatus.COMPLETE

        rights_counts: Dict[str, int] = {r.value: 0 for r in RightsStatus}
        for d in unique_deps:
            raw_ls = d.get("license_status")
            ls = raw_ls.value if isinstance(raw_ls, RightsStatus) else str(raw_ls or RightsStatus.NOT_VERIFIED.value)
            rights_counts[ls] = rights_counts.get(ls, 0) + 1

        verified_dl = sum(1 for d in unique_deps if d.get("retrieval_timestamp_utc") not in (None, "", "unknown"))
        retrieval_summary = {
            "total_tracked_artifacts": len(unique_deps),
            "verified_retrieval_timestamps": verified_dl,
            "unknown_retrieval_timestamps": len(unique_deps) - verified_dl,
            "discovery_scope": "static_seed_manifest",
            "note": "retrieval_timestamp_utc records exact HTTP 200 download time only when acquired via MARSCOPE; pre-existing local files report 'unknown'.",
        }
        rights_summary = {
            "counts": rights_counts,
            "note": "License/rights remain 'not_verified' unless explicitly verified inside source artifact metadata.",
        }

        return self.publish_generation(
            evidence_records=evidence_all,
            rejected_records=rejected_all,
            product_manifests=manifests,
            dependency_artifacts=unique_deps,
            product_audit=product_audit,
            generation_build_status=build_status,
            discovery_scope="static_seed_manifest",
            expected_products_count=len(EXPECTED_COMPOSITION_PRODUCTS),
            missing_expected_products=missing_expected,
            rights_summary=rights_summary,
            retrieval_metadata=retrieval_summary,
            crism_status=crism_status,
            notes=notes,
            simulate_failure_before_cutover=simulate_failure_before_cutover,
        )

    def get_status(self) -> CompositionIndexStatus:
        gen = self.get_active_generation()
        manifest_path = self._manifest_path()
        if gen is None:
            return CompositionIndexStatus(
                index_available=False,
                integrity_status=IntegrityStatus.UNAVAILABLE,
                generation_build_status=GenerationBuildStatus.FAILED,
                rtree_enabled=self.rtree_enabled,
                sqlite_path=str(self.db_path),
                reproducibility_manifest_path=str(manifest_path) if manifest_path.exists() else None,
                notes=["No active composition index generation has been built yet."],
            )
        gen_id = gen["generation_id"]
        with self._connect() as conn:
            species_cnt = conn.execute(
                "SELECT COUNT(DISTINCT canonical_species_id) FROM composition_evidence WHERE generation_id = ?",
                (gen_id,),
            ).fetchone()[0]
            inst_rows = conn.execute(
                "SELECT DISTINCT instrument_id FROM composition_evidence WHERE generation_id = ? ORDER BY instrument_id",
                (gen_id,),
            ).fetchall()
            prod_rows = conn.execute(
                "SELECT product_id, file_path, sha256_checksum, manifest_json FROM ingested_products WHERE generation_id = ?",
                (gen_id,),
            ).fetchall()

        notes = list(json.loads(gen["notes_json"] or "[]"))
        missing_expected = list(json.loads(gen["missing_expected_json"] or "[]")) if "missing_expected_json" in gen.keys() else []
        product_audit = list(json.loads(gen["product_audit_json"] or "[]")) if "product_audit_json" in gen.keys() else []
        dep_artifacts = list(json.loads(gen["dependency_artifacts_json"] or "[]")) if "dependency_artifacts_json" in gen.keys() else []
        rights_summary = dict(json.loads(gen["rights_summary_json"] or "{}")) if "rights_summary_json" in gen.keys() else {}
        retrieval_meta = dict(json.loads(gen["retrieval_metadata_json"] or "{}")) if "retrieval_metadata_json" in gen.keys() else {}
        raw_build_status = gen["generation_build_status"] if "generation_build_status" in gen.keys() else "partial"
        try:
            gen_build_status = GenerationBuildStatus(raw_build_status)
        except ValueError:
            gen_build_status = GenerationBuildStatus.PARTIAL

        missing_files: List[str] = []
        mismatches: List[str] = []
        missing_deps: List[str] = []
        dep_mismatches: List[str] = []
        product_manifests: List[Dict[str, Any]] = []

        for pr in prod_rows:
            fp = Path(pr["file_path"])
            try:
                mobj = json.loads(pr["manifest_json"] or "{}")
                if mobj:
                    product_manifests.append(mobj)
            except Exception:
                pass
            if not fp.exists():
                missing_files.append(fp.name)
                notes.append(f"Indexed source file missing on disk: {fp.name}.")
            elif _sha256_file(fp) != pr["sha256_checksum"]:
                mismatches.append(fp.name)
                notes.append(f"Checksum drift detected for source file {fp.name}; index rebuild required.")

        # Verify ALL dependency artifacts (.LBL, .XML, .FMT, waypoints) on disk
        for dep in dep_artifacts:
            fpath_s = dep.get("file_path")
            if not fpath_s:
                if dep.get("required", True):
                    missing_deps.append(str(dep.get("artifact_id")))
                continue
            dp = Path(fpath_s)
            if not dp.exists():
                missing_deps.append(dp.name)
                notes.append(f"Required dependency artifact missing on disk: {dp.name}.")
            elif dep.get("sha256_checksum") and _sha256_file(dp) != dep["sha256_checksum"]:
                dep_mismatches.append(dp.name)
                notes.append(f"Dependency checksum drift detected for {dp.name}; index rebuild required.")

        # Verify reproducibility manifest JSON presence, syntax, schema keys & generation alignment
        manifest_valid = True
        manifest_errors: List[str] = []
        if not manifest_path.exists():
            manifest_valid = False
            manifest_errors.append(f"Reproducibility manifest missing at {manifest_path.name}.")
        else:
            try:
                m_json = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(m_json, dict):
                    manifest_valid = False
                    manifest_errors.append("Reproducibility manifest JSON root is not an object.")
                else:
                    if m_json.get("generation_id") != gen_id:
                        manifest_valid = False
                        manifest_errors.append(
                            f"Manifest generation_id '{m_json.get('generation_id')}' != active DB '{gen_id}'."
                        )
                    if m_json.get("source_manifest_checksum") != gen["source_manifest_checksum"]:
                        manifest_valid = False
                        manifest_errors.append("Manifest source_manifest_checksum disagrees with active DB generation.")
                    if not isinstance(m_json.get("products"), list):
                        manifest_valid = False
                        manifest_errors.append("Manifest missing valid 'products' list.")
            except Exception as exc:
                manifest_valid = False
                manifest_errors.append(f"Reproducibility manifest corrupt/unparseable: {exc}")

        notes.extend(manifest_errors)
        checksum_valid = (len(missing_files) == 0) and (len(mismatches) == 0) and (len(missing_deps) == 0) and (len(dep_mismatches) == 0)
        deps_valid = (len(missing_deps) == 0) and (len(dep_mismatches) == 0)
        ev_cnt = int(gen["evidence_count"])

        if not manifest_valid:
            integrity = IntegrityStatus.MANIFEST_INVALID
        elif mismatches or dep_mismatches:
            integrity = IntegrityStatus.CHECKSUM_MISMATCH
        elif missing_files or missing_deps:
            integrity = IntegrityStatus.SOURCE_FILES_MISSING
        elif ev_cnt <= 0:
            integrity = IntegrityStatus.INCOMPLETE
        else:
            integrity = IntegrityStatus.VERIFIED

        return CompositionIndexStatus(
            index_available=ev_cnt > 0,
            integrity_status=integrity,
            generation_build_status=gen_build_status,
            active_generation_id=gen_id,
            built_at_utc=gen["created_at_utc"],
            total_validated_evidence=ev_cnt,
            located_evidence_count=int(gen["located_count"]),
            unlocated_evidence_count=int(gen["unlocated_count"]),
            rejected_record_count=int(gen["rejected_count"]),
            species_count=int(species_cnt),
            ingested_products_count=len(prod_rows),
            expected_products_count=int(gen["expected_products_count"]) if "expected_products_count" in gen.keys() else len(EXPECTED_COMPOSITION_PRODUCTS),
            discovery_scope=str(gen["discovery_scope"]) if "discovery_scope" in gen.keys() else "static_seed_manifest",
            instruments_indexed=[r[0] for r in inst_rows],
            checksum_valid=checksum_valid,
            source_dependencies_valid=deps_valid,
            manifest_valid=manifest_valid,
            missing_source_files=missing_files,
            checksum_mismatches=mismatches,
            missing_dependency_files=missing_deps,
            dependency_checksum_mismatches=dep_mismatches,
            missing_expected_products=missing_expected,
            manifest_validation_errors=manifest_errors,
            rtree_enabled=self.rtree_enabled,
            crism_status=gen["crism_status"],
            sqlite_path=str(self.db_path),
            reproducibility_manifest_path=str(manifest_path) if manifest_path.exists() else None,
            product_manifests=product_manifests,
            dependency_artifacts=dep_artifacts,
            product_audit=product_audit,
            rights_summary=rights_summary,
            retrieval_metadata=retrieval_meta,
            notes=notes,
        )

    def query_evidence(
        self,
        species_ids: Iterable[str],
        located_only: bool = True,
        instruments: Optional[List[str]] = None,
        sol_min: Optional[int] = None,
        sol_max: Optional[int] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[CompositionEvidence]:
        """
        Query validated evidence for one or more canonical species IDs from the active generation.
        bbox = (min_lat, max_lat, min_lon_east, max_lon_east), supporting [0, 360) antimeridian wrap.
        """
        gen = self.get_active_generation()
        if gen is None:
            return []
        gen_id = gen["generation_id"]
        sp_list = list(species_ids)
        if not sp_list:
            return []

        placeholders = ",".join("?" for _ in sp_list)
        clauses = [
            "ce.generation_id = ?",
            f"ce.canonical_species_id IN ({placeholders})",
        ]
        params: List[Any] = [gen_id, *sp_list]

        if located_only:
            clauses.append("ce.location_verified = 1")
        if instruments:
            ip = ",".join("?" for _ in instruments)
            clauses.append(f"ce.instrument_id IN ({ip})")
            params.extend(instruments)
        if sol_min is not None:
            clauses.append("ce.sol >= ?")
            params.append(sol_min)
        if sol_max is not None:
            clauses.append("ce.sol <= ?")
            params.append(sol_max)

        join_sql = ""
        if bbox is not None:
            min_lat, max_lat, min_lon_raw, max_lon_raw = bbox
            mn_lon = normalize_longitude_360(min_lon_raw)
            mx_lon = normalize_longitude_360(max_lon_raw)
            if self.rtree_enabled and mn_lon <= mx_lon:
                join_sql = "JOIN evidence_rtree rt ON ce.row_id = rt.row_id"
                clauses.append("rt.min_lat <= ? AND rt.max_lat >= ? AND rt.min_lon <= ? AND rt.max_lon >= ?")
                params.extend([max_lat, min_lat, mx_lon, mn_lon])
            elif mn_lon <= mx_lon:
                clauses.append("ce.min_lat <= ? AND ce.max_lat >= ? AND ce.min_lon_east <= ? AND ce.max_lon_east >= ?")
                params.extend([max_lat, min_lat, mx_lon, mn_lon])
            else:
                # Antimeridian crossing in [0, 360): [mn_lon, 360] OR [0, mx_lon]
                clauses.append("ce.min_lat <= ? AND ce.max_lat >= ? AND (ce.max_lon_east >= ? OR ce.min_lon_east <= ?)")
                params.extend([max_lat, min_lat, mn_lon, mx_lon])

        sql = f"SELECT ce.payload_json FROM composition_evidence ce {join_sql} WHERE {' AND '.join(clauses)}"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [CompositionEvidence.model_validate_json(r[0]) for r in rows]

    def get_evidence_by_id(self, evidence_id: str) -> Optional[CompositionEvidence]:
        gen = self.get_active_generation()
        if gen is None:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM composition_evidence WHERE generation_id = ? AND evidence_id = ? LIMIT 1",
                (gen["generation_id"], evidence_id),
            ).fetchone()
        return CompositionEvidence.model_validate_json(row[0]) if row else None

    def list_rejected_records(self, limit: int = 100, offset: int = 0) -> Tuple[int, List[RejectionRecord]]:
        gen = self.get_active_generation()
        if gen is None:
            return 0, []
        gen_id = gen["generation_id"]
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM rejected_records WHERE generation_id = ?", (gen_id,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT payload_json FROM rejected_records WHERE generation_id = ? ORDER BY row_id DESC LIMIT ? OFFSET ?",
                (gen_id, limit, offset),
            ).fetchall()
        return int(total), [RejectionRecord.model_validate_json(r[0]) for r in rows]
