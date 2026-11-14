"""
NASA MSL Curiosity Observation Parser
Martian Surface Intelligence & Exploration System

Parses verified PDS tables from ChemCam (calibrated LIBS spectra) and REMS (atmospheric logs).
Strictly rejects malformed or empty files and never invents missing coordinates, timestamps, or measurements.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.ingestion.pds_label import extract_pds3_metadata
from app.schemas.observation import Observation, ObservationCoordinates


class MalformedObservationError(ValueError):
    """Raised when a product file lacks required structure or valid parsed measurements."""


def _parse_iso_timestamp(raw: Optional[Any]) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_label_provenance(file_path: Path, label_path: Optional[Path] = None) -> Dict[str, Any]:
    candidates = [label_path] if label_path else []
    candidates.extend([file_path.with_suffix(".lbl"), file_path.with_suffix(".LBL")])
    for cand in candidates:
        if cand and cand.exists():
            try:
                return extract_pds3_metadata(cand)
            except Exception:
                continue
    return {}


class CuriosityDataParser:
    @staticmethod
    def parse_chemcam_psv_file(
        file_path: Path,
        observation_id: Optional[str] = None,
        sol: Optional[int] = None,
        coords: Optional[Tuple[float, float, Optional[float]]] = None,
        label_path: Optional[Path] = None,
        dataset_id: str = "msl_chemcam_sol00010_psv",
    ) -> Observation:
        """
        Parse a ChemCam calibrated spectra table (.TAB) from PDS.
        Never fabricates coordinates or timestamps if absent from product/label.
        Rejects files that contain zero valid spectral samples.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"ChemCam file not found: {file_path}")

        label_meta = _extract_label_provenance(file_path, label_path)
        spectral_samples: List[float] = []
        is_spectral_data = False

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if "Begin Processed Spectral Data" in stripped:
                    is_spectral_data = True
                    continue
                if is_spectral_data and stripped:
                    parts = [p.strip().replace('"', "") for p in stripped.split(",")]
                    try:
                        val = float(parts[0])
                        spectral_samples.append(val)
                        if len(spectral_samples) >= 100:
                            break
                    except ValueError:
                        continue

        if not spectral_samples:
            raise MalformedObservationError(
                f"ChemCam file '{file_path.name}' contains no valid processed spectral channels."
            )

        # Resolve coordinates strictly from explicit argument or label
        location: Optional[ObservationCoordinates] = None
        if coords is not None:
            location = ObservationCoordinates(
                latitude=coords[0],
                longitude=coords[1],
                elevation_m=coords[2],
            )
        elif label_meta.get("target_latitude") is not None and label_meta.get("target_longitude") is not None:
            location = ObservationCoordinates(
                latitude=float(label_meta["target_latitude"]),
                longitude=float(label_meta["target_longitude"]),
                elevation_m=None,
            )

        obs_id = observation_id or str(label_meta.get("product_id") or file_path.stem)
        ts = _parse_iso_timestamp(label_meta.get("start_time"))

        return Observation(
            observation_id=obs_id,
            dataset_id=dataset_id,
            mission="Mars Science Laboratory (MSL)",
            instrument="Chemistry Camera (ChemCam LIBS)",
            observation_timestamp=ts,
            sol=sol,
            location=location,
            crs="IAU2000:49900" if location is not None else None,
            measurement_type="laser_induced_breakdown_spectroscopy_calibrated_photons",
            measurement_value={
                "sampled_channel_count": len(spectral_samples),
                "spectrum_sample": spectral_samples,
            },
            units="photons / (s * cm^2 * sr * nm)",
            processing_level="Calibrated Spectra (RDR Level 4/5)",
            calibration_status="Parsed from PDS ChemCam RDR table",
            quality_flags=["Parsed from local PDS artifact"],
            original_source_reference=str(label_meta.get("product_id") or file_path.name),
            known_limitations=[
                "Point laser sample (~350-500 um beam spot).",
                "Coordinates/timestamp marked null unless present in PDS label metadata.",
            ],
        )

    @staticmethod
    def parse_rems_adr_summary(
        file_path: Path,
        observation_id: Optional[str] = None,
        sol: Optional[int] = None,
        coords: Optional[Tuple[float, float, Optional[float]]] = None,
        label_path: Optional[Path] = None,
        dataset_id: str = "msl_rems_sol00010_adr",
    ) -> Observation:
        """
        Parse a REMS ADR table from PDS Atmospheres Node.
        Rejects malformed files with zero valid measurements; never substitutes fallback numbers.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"REMS file not found: {file_path}")

        label_meta = _extract_label_provenance(file_path, label_path)
        pressures: List[float] = []
        temps: List[float] = []

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                # Support comma-separated and whitespace-separated PDS ASCII tables
                parts = [p.strip().strip('"') for p in (stripped.split(",") if "," in stripped else stripped.split())]
                if len(parts) < 4:
                    continue
                for col in parts:
                    try:
                        val = float(col)
                        # Standard Mars pressure range [400, 1200] Pa vs Kelvin temperature [120, 320] K
                        # Prefer positional columns if numeric
                    except ValueError:
                        continue
                # Positional check matching documented REMS schema if cols 2,3 numeric
                try:
                    p = float(parts[2])
                    t = float(parts[3])
                    if 400.0 <= p <= 1200.0:
                        pressures.append(p)
                    if 120.0 <= t <= 320.0:
                        temps.append(t)
                except (ValueError, IndexError):
                    continue

        if not pressures and not temps:
            raise MalformedObservationError(
                f"REMS file '{file_path.name}' yielded zero valid atmospheric pressure or temperature records."
            )

        location: Optional[ObservationCoordinates] = None
        if coords is not None:
            location = ObservationCoordinates(
                latitude=coords[0],
                longitude=coords[1],
                elevation_m=coords[2],
            )

        obs_id = observation_id or str(label_meta.get("product_id") or file_path.stem)
        ts = _parse_iso_timestamp(label_meta.get("start_time"))

        return Observation(
            observation_id=obs_id,
            dataset_id=dataset_id,
            mission="Mars Science Laboratory (MSL)",
            instrument="Rover Environmental Monitoring Station (REMS)",
            observation_timestamp=ts,
            sol=sol,
            location=location,
            crs="IAU2000:49900" if location is not None else None,
            measurement_type="in_situ_diurnal_atmospheric_measurements",
            measurement_value={
                "mean_pressure_pa": round(sum(pressures) / len(pressures), 2) if pressures else None,
                "min_pressure_pa": round(min(pressures), 2) if pressures else None,
                "max_pressure_pa": round(max(pressures), 2) if pressures else None,
                "mean_temperature_k": round(sum(temps) / len(temps), 2) if temps else None,
                "pressure_record_count": len(pressures),
                "temperature_record_count": len(temps),
            },
            units="Pa (Pressure), K (Temperature)",
            processing_level="Calibrated ADR (Level 6)",
            calibration_status="Parsed from local PDS REMS ADR table",
            quality_flags=["Parsed from local PDS artifact"],
            original_source_reference=str(label_meta.get("product_id") or file_path.name),
            known_limitations=["Local rover thermal bias during daytime operations."],
        )
