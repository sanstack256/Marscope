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
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple
from app.geospatial.crs import normalize_longitude_360
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
    IntegrityStatus,
    RejectionRecord,
)
from app.science.composition.ranking import DEFAULT_HEURISTIC_RANKING_CONFIG
from app.science.composition.validation import EVIDENCE_ID_DETERMINISM_VERSION
from app.science.coordinate_association import CoordinateAssociationService


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class CompositionSpatialIndex:
    """Persistent, transaction-safe SQLite spatial index for verified planetary composition."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.rtree_enabled = self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> bool:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_generations (
                    generation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    source_manifest_checksum TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    located_count INTEGER NOT NULL DEFAULT 0,
                    unlocated_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    crism_status TEXT NOT NULL DEFAULT 'unavailable_no_validated_mineral_cube',
                    notes_json TEXT NOT NULL DEFAULT '[]'
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
            # Graceful migration for pre-existing SQLite databases lacking manifest_json column
            cols = {r[1] for r in conn.execute("PRAGMA table_info(ingested_products)").fetchall()}
            if "manifest_json" not in cols:
                conn.execute("ALTER TABLE ingested_products ADD COLUMN manifest_json TEXT NOT NULL DEFAULT '{}'")
                conn.commit()
            return rtree_ok

    def get_active_generation(self) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM index_generations WHERE status = 'active' ORDER BY created_at_utc DESC LIMIT 1"
            ).fetchone()

    def publish_generation(
        self,
        evidence_records: List[CompositionEvidence],
        rejected_records: List[RejectionRecord],
        product_manifests: Optional[List[Dict[str, Any]]] = None,
        crism_status: str = "unavailable_no_validated_mineral_cube",
        notes: Optional[List[str]] = None,
        generation_id: Optional[str] = None,
    ) -> CompositionIndexStatus:
        """
        Atomically publish a validated composition index generation in a single transaction.
        If any insertion error occurs, rolls back completely leaving the previous generation active.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        manifests = sorted(
            product_manifests or [],
            key=lambda m: (str(m.get("dataset_id", "")), str(m.get("product_id", ""))),
        )
        manifest_digest = hashlib.sha256(
            json.dumps(
                [(m.get("product_id", ""), m.get("sha256_checksum", "")) for m in manifests],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        ev_digest = hashlib.sha256(
            "|".join(e.evidence_id for e in sorted(evidence_records, key=lambda x: x.evidence_id)).encode("utf-8")
        ).hexdigest()
        gen_id = generation_id or f"gen_{hashlib.sha256(f'{manifest_digest}|{ev_digest}|{len(rejected_records)}'.encode()).hexdigest()[:12]}"

        located_count = sum(1 for e in evidence_records if e.location_verified)
        unlocated_count = len(evidence_records) - located_count

        with self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE;")
                # Clear prior rows cleanly if rebuilding the exact same deterministic content generation_id
                conn.execute("DELETE FROM composition_evidence WHERE generation_id = ?", (gen_id,))
                conn.execute("DELETE FROM rejected_records WHERE generation_id = ?", (gen_id,))
                conn.execute("DELETE FROM ingested_products WHERE generation_id = ?", (gen_id,))
                conn.execute("DELETE FROM index_generations WHERE generation_id = ?", (gen_id,))

                conn.execute(
                    """
                    INSERT INTO index_generations (
                        generation_id, status, created_at_utc, source_manifest_checksum,
                        evidence_count, located_count, unlocated_count, rejected_count,
                        crism_status, notes_json
                    ) VALUES (?, 'building', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gen_id,
                        now_utc,
                        manifest_digest,
                        len(evidence_records),
                        located_count,
                        unlocated_count,
                        len(rejected_records),
                        crism_status,
                        json.dumps(notes or []),
                    ),
                )

                for m in manifests:
                    conn.execute(
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
                    cur = conn.execute(
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
                        self.rtree_enabled
                        and ev_copy.location_verified
                        and ev_copy.latitude is not None
                        and min_lon is not None
                        and max_lon is not None
                    ):
                        mn_lat = ev_copy.min_lat if ev_copy.min_lat is not None else ev_copy.latitude
                        mx_lat = ev_copy.max_lat if ev_copy.max_lat is not None else ev_copy.latitude
                        if min_lon <= max_lon:
                            conn.execute(
                                "INSERT INTO evidence_rtree (row_id, min_lon, max_lon, min_lat, max_lat) VALUES (?, ?, ?, ?, ?)",
                                (row_id, min_lon, max_lon, mn_lat, mx_lat),
                            )

                for rej in rejected_records:
                    conn.execute(
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

                # Atomic cutover: supersede prior active generations and activate new one
                conn.execute("UPDATE index_generations SET status = 'superseded' WHERE status = 'active'")
                conn.execute("UPDATE index_generations SET status = 'active' WHERE generation_id = ?", (gen_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        manifest_path = self.db_path.parent / "reproducibility_manifest.json"
        repro_payload = {
            "manifest_format_version": "reproducibility_manifest_v1",
            "generation_id": gen_id,
            "built_at_utc": now_utc,
            "source_manifest_checksum": manifest_digest,
            "sqlite_path": str(self.db_path),
            "determinism_version": EVIDENCE_ID_DETERMINISM_VERSION,
            "validation_pipeline_version": "12_stage_v2",
            "ranking_config_id": DEFAULT_HEURISTIC_RANKING_CONFIG.ranking_config_id,
            "ranking_config_version": DEFAULT_HEURISTIC_RANKING_CONFIG.ranking_config_version,
            "total_validated_evidence": len(evidence_records),
            "located_evidence_count": located_count,
            "unlocated_evidence_count": unlocated_count,
            "rejected_record_count": len(rejected_records),
            "crism_status": crism_status,
            "products": manifests,
            "notes": notes or [],
        }
        tmp_manifest = manifest_path.with_suffix(".tmp")
        tmp_manifest.write_text(json.dumps(repro_payload, indent=2), encoding="utf-8")
        tmp_manifest.replace(manifest_path)

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
    ) -> Dict[str, Any]:
        st = file_path.stat()
        return {
            "dataset_id": dataset_id,
            "product_id": product_id,
            "source_url": source_url,
            "file_path": str(file_path),
            "byte_size": int(st.st_size),
            "source_mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "sha256_checksum": _sha256_file(file_path),
            "license": "NASA Planetary Data System (PDS) Public Domain",
            "label_path": str(label_path) if label_path else None,
            "schema_version": schema_version,
            "parser_id": parser_id,
            "parser_version": parser_version,
            "validation_pipeline_version": "12_stage_v2",
            "determinism_version": EVIDENCE_ID_DETERMINISM_VERSION,
            "coordinate_association_method": coord_method,
            "record_count": int(record_count),
            "rejected_count": int(rejected_count),
        }

    def rebuild_from_raw_directory(
        self,
        raw_dir: Path,
        processed_dir: Path,
    ) -> CompositionIndexStatus:
        """
        Discover and parse all verified NASA PDS raw artifacts inside raw_dir, associate
        documented coordinates via JPL MSL_waypoints.json when present, run the 12-stage
        validation pipeline on every candidate, and atomically publish a fresh SQLite index
        plus reproducibility_manifest.json.
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

        coord_svc = CoordinateAssociationService()
        wp_candidates = _glob_ci("*waypoints*.json")
        notes: List[str] = []
        manifests: List[Dict[str, Any]] = []
        if wp_candidates:
            wp_path = wp_candidates[0]
            wp_count = coord_svc.load_waypoints_geojson(wp_path)
            notes.append(f"Loaded {wp_count} JPL MSL traverse waypoints from {wp_path.name}.")
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
        else:
            notes.append("No JPL MSL_waypoints.json file in raw_dir; RMC coordinate joins will mark records unlocated.")

        evidence_all: List[CompositionEvidence] = []
        rejected_all: List[RejectionRecord] = []

        if raw_dir.exists():
            # 1. APXS Supplement CSVs
            apxs_files = sorted({p for p in _glob_ci("*2021je007171r*.csv") + _glob_ci("*apxs*.csv")})
            for csv_path in apxs_files:
                xml_lbl = _find_companion(csv_path, (".xml", ".XML"))
                url = "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/ds01_2021je007171r.csv"
                acc, rej = ApxsEvidenceAdapter.adapt_csv(
                    csv_path,
                    source_dataset_id="msl_apxs_supplement_sols_0_3076",
                    product_id=csv_path.stem.upper(),
                    provenance_url=url,
                    label_path=xml_lbl,
                )
                evidence_all.extend(acc)
                rejected_all.extend(rej)
                manifests.append(
                    self._build_product_manifest(
                        dataset_id="msl_apxs_supplement_sols_0_3076",
                        product_id=csv_path.stem.upper(),
                        file_path=csv_path,
                        source_url=url,
                        label_path=xml_lbl,
                        schema_version=acc[0].schema_version if acc and acc[0].schema_version else "apxs_csv_header",
                        parser_id="apxs_pds4_schema_parser",
                        parser_version="2.0.0",
                        coord_method="gale_eqc_target_pyproj",
                        record_count=len(acc),
                        rejected_count=len(rej),
                    )
                )

            # 2. ChemCam MOC Tables
            for moc_csv in _glob_ci("moc_*.csv"):
                lbl = _find_companion(moc_csv, (".lbl", ".LBL"))
                url = f"https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/{moc_csv.name}"
                acc, rej = ChemCamEvidenceAdapter.adapt_moc_csv(
                    moc_csv,
                    label_path=lbl,
                    source_dataset_id=f"msl_chemcam_{moc_csv.stem.lower()}",
                    coord_service=coord_svc,
                    provenance_url=url,
                )
                evidence_all.extend(acc)
                rejected_all.extend(rej)
                manifests.append(
                    self._build_product_manifest(
                        dataset_id=f"msl_chemcam_{moc_csv.stem.lower()}",
                        product_id=moc_csv.stem.upper(),
                        file_path=moc_csv,
                        source_url=url,
                        label_path=lbl,
                        schema_version=acc[0].schema_version if acc and acc[0].schema_version else "pds3_moc",
                        parser_id="chemcam_moc_schema_parser",
                        parser_version="2.0.0",
                        coord_method="rmc_site_drive_rover_station",
                        record_count=len(acc),
                        rejected_count=len(rej),
                    )
                )

            # 3. CheMin Mineral RDR5 Tables
            for cm_csv in _glob_ci("cm*min*.csv"):
                lbl = _find_companion(cm_csv, (".lbl", ".LBL"))
                url = f"https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/{cm_csv.name}"
                acc, rej = CheMinEvidenceAdapter.adapt_rdr5_csv(
                    cm_csv,
                    label_path=lbl,
                    source_dataset_id=f"msl_chemin_{cm_csv.stem.lower()}",
                    coord_service=coord_svc,
                    extra_structure_dirs=[raw_dir],
                    provenance_url=url,
                )
                evidence_all.extend(acc)
                rejected_all.extend(rej)
                manifests.append(
                    self._build_product_manifest(
                        dataset_id=f"msl_chemin_{cm_csv.stem.lower()}",
                        product_id=cm_csv.stem.upper(),
                        file_path=cm_csv,
                        source_url=url,
                        label_path=lbl,
                        schema_version=acc[0].schema_version if acc and acc[0].schema_version else "pds3_chemin_fmt",
                        parser_id="chemin_rdr5_schema_parser",
                        parser_version="2.0.0",
                        coord_method="rmc_site_drive_rover_station",
                        record_count=len(acc),
                        rejected_count=len(rej),
                    )
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
        return self.publish_generation(
            evidence_records=evidence_all,
            rejected_records=rejected_all,
            product_manifests=manifests,
            crism_status=crism_status,
            notes=notes,
        )

    def get_status(self) -> CompositionIndexStatus:
        gen = self.get_active_generation()
        manifest_path = self.db_path.parent / "reproducibility_manifest.json"
        if gen is None:
            return CompositionIndexStatus(
                index_available=False,
                integrity_status=IntegrityStatus.UNAVAILABLE,
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
        missing_files: List[str] = []
        mismatches: List[str] = []
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

        checksum_valid = (len(missing_files) == 0) and (len(mismatches) == 0)
        ev_cnt = int(gen["evidence_count"])
        if mismatches:
            integrity = IntegrityStatus.CHECKSUM_MISMATCH
        elif missing_files:
            integrity = IntegrityStatus.SOURCE_FILES_MISSING
        elif ev_cnt <= 0:
            integrity = IntegrityStatus.INCOMPLETE
        else:
            integrity = IntegrityStatus.VERIFIED

        return CompositionIndexStatus(
            index_available=ev_cnt > 0,
            integrity_status=integrity,
            active_generation_id=gen_id,
            built_at_utc=gen["created_at_utc"],
            total_validated_evidence=ev_cnt,
            located_evidence_count=int(gen["located_count"]),
            unlocated_evidence_count=int(gen["unlocated_count"]),
            rejected_record_count=int(gen["rejected_count"]),
            species_count=int(species_cnt),
            ingested_products_count=len(prod_rows),
            instruments_indexed=[r[0] for r in inst_rows],
            checksum_valid=checksum_valid,
            missing_source_files=missing_files,
            checksum_mismatches=mismatches,
            rtree_enabled=self.rtree_enabled,
            crism_status=gen["crism_status"],
            sqlite_path=str(self.db_path),
            reproducibility_manifest_path=str(manifest_path) if manifest_path.exists() else None,
            product_manifests=product_manifests,
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
