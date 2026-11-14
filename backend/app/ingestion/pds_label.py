"""
NASA PDS3 Label (.LBL) Metadata Parser
Martian Surface Intelligence & Exploration System

Parses authentic PDS3 ODL keyword-value labels to extract authoritative
CRS, radii, coordinate conventions, scale/offset, units, bounds, and timestamps.
Never invents values absent from the label.
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional


def _strip_pds_value(raw: str) -> Any:
    val = raw.strip().strip('"').strip("'").strip()
    if not val or val.upper() == "N/A":
        return None
    # Remove trailing <UNIT> annotations while extracting numeric part if applicable
    unit_match = re.match(r"^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*<([^>]+)>$", val)
    if unit_match:
        num_str, unit_str = unit_match.groups()
        try:
            return {"value": float(num_str), "unit": unit_str.strip()}
        except ValueError:
            return val
    # Plain numeric check
    if re.fullmatch(r"[+-]?\d+", val):
        return int(val)
    if re.fullmatch(r"[+-]?\d+\.\d+(?:[eE][+-]?\d+)?", val):
        return float(val)
    return val


def parse_pds3_label_text(text: str) -> Dict[str, Any]:
    """
    Parse a PDS3 ASCII label string into structured key-value metadata.
    Tracks nested OBJECT sections (e.g., IMAGE, IMAGE_MAP_PROJECTION).
    """
    root: Dict[str, Any] = {}
    objects: Dict[str, Dict[str, Any]] = {}
    current_object: Optional[str] = None

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Strip inline PDS comments /* ... */
        line_no_comment = re.sub(r"/\*.*?\*/", "", line).strip()
        if not line_no_comment:
            i += 1
            continue

        if "=" in line_no_comment:
            key, val_part = line_no_comment.split("=", 1)
            key = key.strip().upper()
            val_part = val_part.strip()

            # Handle multi-line quoted values
            if val_part.startswith('"') and val_part.count('"') == 1:
                buf = [val_part]
                while i + 1 < len(lines):
                    i += 1
                    nxt = lines[i].strip()
                    buf.append(nxt)
                    if '"' in nxt:
                        break
                val_part = " ".join(buf)

            if key == "OBJECT":
                current_object = str(_strip_pds_value(val_part))
                objects.setdefault(current_object, {})
                i += 1
                continue
            elif key == "END_OBJECT":
                current_object = None
                i += 1
                continue

            parsed_val = _strip_pds_value(val_part)
            if current_object:
                objects[current_object][key] = parsed_val
            else:
                root[key] = parsed_val

        elif line_no_comment.upper() == "END":
            break
        i += 1

    root["_OBJECTS"] = objects
    return root


def extract_pds3_metadata(label_path: Path) -> Dict[str, Any]:
    """
    Read and normalize geospatial & scientific metadata from a local PDS3 .LBL file.
    """
    if not label_path.exists():
        raise FileNotFoundError(f"PDS3 label not found: {label_path}")

    raw_text = label_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_pds3_label_text(raw_text)
    objs = parsed.get("_OBJECTS", {})
    img_obj = objs.get("IMAGE", {})
    proj_obj = objs.get("IMAGE_MAP_PROJECTION", {})

    def _num(entry: Any) -> Optional[float]:
        if isinstance(entry, dict) and "value" in entry:
            return float(entry["value"])
        if isinstance(entry, (int, float)):
            return float(entry)
        return None

    def _radius_m(entry: Any) -> Optional[float]:
        if isinstance(entry, dict) and "value" in entry:
            val = float(entry["value"])
            unit = str(entry.get("unit", "")).upper()
            return val * 1000.0 if unit == "KM" else val
        if isinstance(entry, (int, float)):
            # PDS3 radius values around 3396 are km
            return float(entry) * 1000.0 if float(entry) < 10000.0 else float(entry)
        return None

    def _scale_m(entry: Any) -> Optional[float]:
        if isinstance(entry, dict) and "value" in entry:
            val = float(entry["value"])
            unit = str(entry.get("unit", "")).upper()
            if "KM" in unit:
                return val * 1000.0
            return val
        if isinstance(entry, (int, float)):
            return float(entry)
        return None

    # Normalize units
    raw_unit = img_obj.get("UNIT") or parsed.get("UNIT")
    norm_unit = "unknown"
    if isinstance(raw_unit, str):
        u_low = raw_unit.strip().lower()
        if u_low in {"meter", "meters", "m"}:
            norm_unit = "meters"
        elif u_low:
            norm_unit = raw_unit.strip()

    # Radii & CRS inference strictly from label parameters
    a_m = _radius_m(proj_obj.get("A_AXIS_RADIUS"))
    b_m = _radius_m(proj_obj.get("B_AXIS_RADIUS"))
    c_m = _radius_m(proj_obj.get("C_AXIS_RADIUS"))
    radii = None
    if a_m and b_m:
        radii = {"a": a_m, "b": b_m, "c": c_m or b_m}

    lon_dir = str(proj_obj.get("POSITIVE_LONGITUDE_DIRECTION") or "").strip().title() or "unknown"
    lat_type = str(proj_obj.get("COORDINATE_SYSTEM_NAME") or "").strip().title() or "unknown"
    min_lon = _num(proj_obj.get("WESTERNMOST_LONGITUDE"))
    max_lon = _num(proj_obj.get("EASTERNMOST_LONGITUDE"))
    lon_range = "unknown"
    if min_lon is not None and max_lon is not None:
        if max_lon > 180.0:
            lon_range = "[0, 360]"
        elif min_lon < 0.0:
            lon_range = "[-180, 180]"
        else:
            lon_range = "[0, 360]" if max_lon == 360.0 else "[-180, 180]"

    return {
        "product_id": parsed.get("PRODUCT_ID"),
        "data_set_id": parsed.get("DATA_SET_ID"),
        "spacecraft_name": parsed.get("SPACECRAFT_NAME"),
        "instrument_name": parsed.get("INSTRUMENT_NAME") or parsed.get("INSTRUMENT_ID"),
        "target_name": parsed.get("TARGET_NAME"),
        "start_time": parsed.get("START_TIME"),
        "stop_time": parsed.get("STOP_TIME"),
        "product_creation_time": parsed.get("PRODUCT_CREATION_TIME"),
        "units": norm_unit,
        "missing_constant": _num(img_obj.get("MISSING_CONSTANT")) or _num(img_obj.get("INVALID_CONSTANT")),
        "scaling_factor": _num(img_obj.get("SCALING_FACTOR")) or 1.0,
        "offset": _num(img_obj.get("OFFSET")) or 0.0,
        "lines": img_obj.get("LINES"),
        "line_samples": img_obj.get("LINE_SAMPLES"),
        "sample_bits": img_obj.get("SAMPLE_BITS"),
        "sample_type": img_obj.get("SAMPLE_TYPE"),
        "map_projection": proj_obj.get("MAP_PROJECTION_TYPE") or "unknown",
        "latitude_convention": lat_type,
        "longitude_direction": lon_dir,
        "longitude_range": lon_range,
        "planetary_radii_m": radii,
        "map_resolution_ppd": _num(proj_obj.get("MAP_RESOLUTION")),
        "map_scale_m_per_px": _scale_m(proj_obj.get("MAP_SCALE")),
        "bounds": {
            "min_latitude": _num(proj_obj.get("MINIMUM_LATITUDE")),
            "max_latitude": _num(proj_obj.get("MAXIMUM_LATITUDE")),
            "min_longitude": min_lon,
            "max_longitude": max_lon,
            "center_latitude": _num(proj_obj.get("CENTER_LATITUDE")),
            "center_longitude": _num(proj_obj.get("CENTER_LONGITUDE")),
        },
        "target_latitude": _num(parsed.get("TARGET_LATITUDE")),
        "target_longitude": _num(parsed.get("TARGET_LONGITUDE")),
    }
