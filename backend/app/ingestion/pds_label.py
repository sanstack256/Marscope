"""
PDS3 ODL Label & Format (.FMT) Parser
Martian Surface Intelligence & Exploration System

Extracts verified planetary metadata, nested OBJECT/GROUP blocks, ordered
COLUMN/FIELD schemas, data pointers (^TABLE, ^SPREADSHEET, ^HEADER), external
^STRUCTURE (.FMT) includes, and MSL ROVER_MOTION_COUNTER tuples from PDS3 ODL labels.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple


_NUM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?$")


def strip_odl_comments(text: str) -> str:
    """Strip /* ... */ PDS3 ODL comments outside double-quoted strings."""
    out: List[str] = []
    i = 0
    n = len(text)
    in_quote = False
    while i < n:
        ch = text[i]
        if ch == '"':
            in_quote = not in_quote
            out.append(ch)
            i += 1
        elif not in_quote and ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _clean_scalar(raw: str) -> str:
    val = raw.strip()
    if "<" in val and ">" in val and not (val.startswith('"') and val.endswith('"')):
        val = re.sub(r"\s*<[^>]+>", "", val).strip()
    if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        val = val[1:-1].strip()
    elif len(val) >= 2 and val.startswith("'") and val.endswith("'"):
        val = val[1:-1].strip()
    return re.sub(r"\s+", " ", val)


def _split_top_level_items(inner: str) -> List[str]:
    """Split comma-separated items while respecting quotes."""
    items: List[str] = []
    buf: List[str] = []
    in_quote = False
    for ch in inner:
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
        elif ch == "," and not in_quote:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf).strip())
    return [it for it in items if it != ""]


def parse_odl_value(raw: str) -> Any:
    """Parse an ODL scalar, unit-annotated value, tuple (...), or set {...}."""
    s = raw.strip()
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("{") and s.endswith("}")):
        inner = s[1:-1].strip()
        return [parse_odl_value(part) for part in _split_top_level_items(inner)]

    # Preserve unit tag when inspecting pointers like ("FILE.CSV", 1859 <BYTES>)
    cleaned = _clean_scalar(s)
    if s.startswith('"') and s.endswith('"'):
        return cleaned
    if _NUM_RE.match(cleaned):
        num_str = cleaned.replace("D", "E").replace("d", "e")
        try:
            if "." not in num_str and "e" not in num_str.lower():
                return int(num_str)
            return float(num_str)
        except ValueError:
            return cleaned
    return cleaned


def parse_pds3_pointer(raw_pointer: Any) -> Optional[Dict[str, Any]]:
    """
    Parse PDS3 file pointer expressions such as:
      - "FILE.TAB" -> {"file": "FILE.TAB", "offset": 1, "unit": "RECORDS"}
      - ("FILE.CSV", 1859 <BYTES>) -> {"file": "FILE.CSV", "offset": 1859, "unit": "BYTES"}
      - ("FILE.TAB", 30) -> {"file": "FILE.TAB", "offset": 30, "unit": "RECORDS"}
      - 30 -> {"file": None, "offset": 30, "unit": "RECORDS"}
    """
    if raw_pointer is None:
        return None
    if isinstance(raw_pointer, int):
        return {"file": None, "offset": raw_pointer, "unit": "RECORDS"}
    if isinstance(raw_pointer, str):
        s = raw_pointer.strip()
        if s.startswith("(") and s.endswith(")"):
            parts = _split_top_level_items(s[1:-1])
            fname = _clean_scalar(parts[0]) if parts else None
            offset = 1
            unit = "RECORDS"
            if len(parts) >= 2:
                sec = parts[1].strip()
                if "<BYTES>" in sec.upper():
                    unit = "BYTES"
                sec_clean = _clean_scalar(sec)
                try:
                    offset = int(float(sec_clean))
                except ValueError:
                    offset = 1
            return {"file": fname, "offset": offset, "unit": unit}
        return {"file": _clean_scalar(s), "offset": 1, "unit": "RECORDS"}
    if isinstance(raw_pointer, list) and raw_pointer:
        fname = str(raw_pointer[0]) if raw_pointer[0] is not None else None
        offset = 1
        if len(raw_pointer) > 1 and isinstance(raw_pointer[1], (int, float)):
            offset = int(raw_pointer[1])
        return {"file": fname, "offset": offset, "unit": "RECORDS"}
    return None


def _tokenize_odl_statements(text: str) -> List[Tuple[str, str]]:
    """
    Collect key = value assignments across multiline ODL statements.
    """
    cleaned = strip_odl_comments(text)
    statements: List[Tuple[str, str]] = []
    cur_key: Optional[str] = None
    cur_val_parts: List[str] = []
    open_parens = 0
    open_braces = 0
    in_quote = False

    def flush() -> None:
        nonlocal cur_key, cur_val_parts
        if cur_key is not None:
            statements.append((cur_key, " ".join(cur_val_parts).strip()))
            cur_key = None
            cur_val_parts = []

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "END" and cur_key is None:
            break

        # Detect new assignment when not inside multiline quote/tuple/set
        if "=" in line and not in_quote and open_parens == 0 and open_braces == 0:
            left, right = line.split("=", 1)
            candidate_key = left.strip().upper()
            # Valid ODL keys have no spaces
            if candidate_key and " " not in candidate_key:
                flush()
                cur_key = candidate_key
                val_str = right.strip()
                cur_val_parts = [val_str]
                # Track quotes and parens on this line
                for ch in val_str:
                    if ch == '"':
                        in_quote = not in_quote
                    elif not in_quote:
                        if ch == "(":
                            open_parens += 1
                        elif ch == ")" and open_parens > 0:
                            open_parens -= 1
                        elif ch == "{":
                            open_braces += 1
                        elif ch == "}" and open_braces > 0:
                            open_braces -= 1
                if val_str == "" and not in_quote:
                    # Value begins on the next line
                    pass
                continue

        if cur_key is not None:
            cur_val_parts.append(line)
            for ch in line:
                if ch == '"':
                    in_quote = not in_quote
                elif not in_quote:
                    if ch == "(":
                        open_parens += 1
                    elif ch == ")" and open_parens > 0:
                        open_parens -= 1
                    elif ch == "{":
                        open_braces += 1
                    elif ch == "}" and open_braces > 0:
                        open_braces -= 1

    flush()
    return statements


def parse_pds3_odl(text: str) -> Dict[str, Any]:
    """
    Parse a PDS3 ODL label or .FMT structure fragment into nested dicts, preserving
    ordered lists for repeated OBJECTs (e.g., COLUMN, FIELD) and raw pointer expressions.
    """
    root: Dict[str, Any] = {
        "_OBJECTS": {},
        "_GROUPS": {},
        "_RAW_POINTERS": {},
        "_COLUMNS": [],
    }
    stack: List[Tuple[str, str, Dict[str, Any]]] = []  # (kind: OBJECT|GROUP, name, node)

    def current_node() -> Dict[str, Any]:
        return stack[-1][2] if stack else root

    for key, raw_val in _tokenize_odl_statements(text):
        val = _clean_scalar(raw_val)

        if key == "OBJECT":
            obj_name = val.upper()
            node: Dict[str, Any] = {"_TYPE": obj_name, "_OBJECTS": {}, "_GROUPS": {}}
            parent = current_node()
            # Store singular reference for backward compatibility AND list reference for schema tables
            parent.setdefault("_OBJECT_LISTS", {}).setdefault(obj_name, []).append(node)
            if obj_name in {"COLUMN", "FIELD"}:
                parent.setdefault("_COLUMNS", []).append(node)
                if not stack:
                    root["_COLUMNS"].append(node)
            parent.setdefault("_OBJECTS", {})[obj_name] = node
            stack.append(("OBJECT", obj_name, node))
            continue

        if key == "END_OBJECT":
            if stack and stack[-1][0] == "OBJECT":
                stack.pop()
            continue

        if key == "GROUP":
            grp_name = val.upper()
            node = {"_TYPE": grp_name, "_OBJECTS": {}, "_GROUPS": {}}
            parent = current_node()
            parent.setdefault("_GROUP_LISTS", {}).setdefault(grp_name, []).append(node)
            parent.setdefault("_GROUPS", {})[grp_name] = node
            stack.append(("GROUP", grp_name, node))
            continue

        if key == "END_GROUP":
            if stack and stack[-1][0] == "GROUP":
                stack.pop()
            continue

        target = current_node()
        if key.startswith("^"):
            target.setdefault("_RAW_POINTERS", {})[key] = raw_val
        target[key] = val

    return root


def parse_pds3_label(text: str) -> Dict[str, Any]:
    """Backward-compatible ODL label parser wrapper."""
    return parse_pds3_odl(text)


def load_pds3_columns_and_structure(
    label_path: Path,
    table_object_names: Optional[Tuple[str, ...]] = None,
    extra_structure_dirs: Optional[List[Path]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parse a PDS3 .LBL file and resolve any inline COLUMN/FIELD definitions as well as
    external ^STRUCTURE (.FMT) schema definitions referenced inside the label or table object.
    """
    if not label_path.exists():
        raise FileNotFoundError(f"PDS3 label not found: {label_path}")

    parsed = parse_pds3_odl(label_path.read_text(encoding="utf-8", errors="replace"))
    search_dirs = [label_path.parent]
    if extra_structure_dirs:
        search_dirs.extend(extra_structure_dirs)

    columns: List[Dict[str, Any]] = []

    def _collect_from_node(node: Dict[str, Any]) -> None:
        # Recursively check sub-objects if needed, preserving order
        raw_struct = node.get("^STRUCTURE")
        if raw_struct:
            struct_name = _clean_scalar(str(raw_struct)).strip('"').strip("'")
            fmt_path: Optional[Path] = None
            for d in search_dirs:
                for cand_name in (struct_name, struct_name.lower(), struct_name.upper()):
                    cand = d / cand_name
                    if cand.exists():
                        fmt_path = cand
                        break
                if fmt_path:
                    break
            if fmt_path is not None:
                fmt_parsed = parse_pds3_odl(fmt_path.read_text(encoding="utf-8", errors="replace"))
                columns.extend(fmt_parsed.get("_COLUMNS", []))

        for col in node.get("_COLUMNS", []):
            columns.append(col)

    objs = parsed.get("_OBJECTS", {})
    if table_object_names:
        for tname in table_object_names:
            tkey = tname.upper()
            if tkey in objs:
                _collect_from_node(objs[tkey])
    else:
        for tkey, node in objs.items():
            if tkey != "HEADER":
                _collect_from_node(node)

    if not columns and parsed.get("_COLUMNS"):
        columns.extend(parsed["_COLUMNS"])

    return parsed, columns


def _parse_num(val_str: Optional[str]) -> Optional[float]:
    if not val_str:
        return None
    cleaned = _clean_scalar(val_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_rmc_info(parsed: Dict[str, Any]) -> Dict[str, Any]:
    raw_rmc = parsed.get("ROVER_MOTION_COUNTER")
    raw_names = parsed.get("ROVER_MOTION_COUNTER_NAME")
    if not raw_rmc:
        return {}
    rmc_vals = parse_odl_value(f"({raw_rmc})" if not str(raw_rmc).strip().startswith("(") else str(raw_rmc))
    if not isinstance(rmc_vals, list):
        return {}
    names = []
    if raw_names:
        parsed_names = parse_odl_value(
            f"({raw_names})" if not str(raw_names).strip().startswith("(") else str(raw_names)
        )
        if isinstance(parsed_names, list):
            names = [str(n).upper() for n in parsed_names]

    info: Dict[str, Any] = {"rmc_values": rmc_vals}
    if names and len(names) == len(rmc_vals):
        info["rmc_named"] = dict(zip(names, rmc_vals))
    if len(rmc_vals) >= 2 and all(isinstance(v, (int, float)) for v in rmc_vals[:2]):
        site = int(rmc_vals[0])
        drive = int(rmc_vals[1])
        info["site"] = site
        info["drive"] = drive
        info["rmc_key"] = f"{site}_{drive}"
    return info


def extract_pds3_metadata(label_path: Path) -> Dict[str, Any]:
    """
    Extract verified cartographic, observation, unit, table-schema, and planetary radii
    metadata from a PDS3 .LBL file.
    """
    if not label_path.exists():
        raise FileNotFoundError(f"PDS3 label not found: {label_path}")

    text = label_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_pds3_odl(text)

    img_obj = parsed.get("_OBJECTS", {}).get("IMAGE", {})
    proj_obj = parsed.get("_OBJECTS", {}).get("IMAGE_MAP_PROJECTION", {})
    tbl_obj = (
        parsed.get("_OBJECTS", {}).get("TABLE")
        or parsed.get("_OBJECTS", {}).get("SPREADSHEET")
        or parsed.get("_OBJECTS", {}).get("REMS_SCIENCE_TABLE")
        or {}
    )

    # Units
    raw_unit = (
        img_obj.get("UNIT")
        or tbl_obj.get("UNIT")
        or parsed.get("UNIT")
        or ("DIGITAL_NUMBER" if "CHEMCAM-PSV" in str(parsed.get("PRODUCT_TYPE", "")).upper() else "")
    )
    unit_norm = "unknown"
    if raw_unit:
        u_low = str(raw_unit).lower()
        if u_low in {"meter", "meters", "m"}:
            unit_norm = "meters"
        elif u_low in {"km", "kilometer", "kilometers"}:
            unit_norm = "kilometers"
        else:
            unit_norm = str(raw_unit).strip()

    # Scaling & Offset & Missing constant
    scaling = _parse_num(img_obj.get("SCALING_FACTOR"))
    offset = _parse_num(img_obj.get("OFFSET"))
    missing = _parse_num(img_obj.get("MISSING_CONSTANT") or tbl_obj.get("MISSING_CONSTANT"))

    # Bounds
    min_lat = _parse_num(proj_obj.get("MINIMUM_LATITUDE"))
    max_lat = _parse_num(proj_obj.get("MAXIMUM_LATITUDE"))
    west_lon = _parse_num(proj_obj.get("WESTERNMOST_LONGITUDE"))
    east_lon = _parse_num(proj_obj.get("EASTERNMOST_LONGITUDE"))
    map_scale_km = _parse_num(proj_obj.get("MAP_SCALE"))
    map_res_ppd = _parse_num(proj_obj.get("MAP_RESOLUTION"))

    # Coordinate System & Radii
    coord_sys = proj_obj.get("COORDINATE_SYSTEM_NAME") or "unknown"
    lon_dir_raw = proj_obj.get("POSITIVE_LONGITUDE_DIRECTION") or "unknown"
    lon_dir = (
        "East"
        if "EAST" in str(lon_dir_raw).upper()
        else ("West" if "WEST" in str(lon_dir_raw).upper() else "unknown")
    )
    a_km = _parse_num(proj_obj.get("A_AXIS_RADIUS"))
    b_km = _parse_num(proj_obj.get("B_AXIS_RADIUS"))
    c_km = _parse_num(proj_obj.get("C_AXIS_RADIUS"))

    radii_m = None
    if a_km and c_km:
        radii_m = {
            "a": a_km * 1000.0,
            "b": (b_km * 1000.0) if b_km else a_km * 1000.0,
            "c": c_km * 1000.0,
        }

    # Longitude range convention
    lon_range = "unknown"
    if west_lon is not None and east_lon is not None:
        if west_lon >= 0.0 and east_lon <= 360.0:
            lon_range = "[0, 360]"
        elif west_lon >= -180.0 and east_lon <= 180.0:
            lon_range = "[-180, 180]"

    raw_pointers = {
        k: parse_pds3_pointer(v)
        for k, v in parsed.get("_RAW_POINTERS", {}).items()
    }

    sol_num: Optional[int] = None
    if parsed.get("PLANET_DAY_NUMBER") is not None:
        try:
            sol_num = int(float(str(parsed["PLANET_DAY_NUMBER"])))
        except ValueError:
            sol_num = None

    return {
        "product_id": parsed.get("PRODUCT_ID"),
        "product_type": parsed.get("PRODUCT_TYPE"),
        "data_set_id": parsed.get("DATA_SET_ID"),
        "instrument_id": parsed.get("INSTRUMENT_ID"),
        "instrument_name": parsed.get("INSTRUMENT_NAME"),
        "laser_mode": parsed.get("MSL:LASER_MODE"),
        "planet_day_number": sol_num,
        "start_time": parsed.get("START_TIME"),
        "stop_time": parsed.get("STOP_TIME"),
        "target_name": parsed.get("TARGET_NAME"),
        "source_product_id": parsed.get("SOURCE_PRODUCT_ID"),
        "record_type": parsed.get("RECORD_TYPE"),
        "record_bytes": int(parsed["RECORD_BYTES"]) if str(parsed.get("RECORD_BYTES", "")).isdigit() else None,
        "file_records": int(parsed["FILE_RECORDS"]) if str(parsed.get("FILE_RECORDS", "")).isdigit() else None,
        "pointers": raw_pointers,
        "rover_motion_counter": _extract_rmc_info(parsed),
        "units": unit_norm,
        "scaling_factor": scaling,
        "offset": offset,
        "missing_constant": missing,
        "map_projection_type": proj_obj.get("MAP_PROJECTION_TYPE"),
        "latitude_convention": (
            coord_sys.title() if str(coord_sys).upper() in {"PLANETOCENTRIC", "PLANETOGRAPHIC"} else str(coord_sys)
        ),
        "longitude_direction": lon_dir,
        "longitude_range": lon_range,
        "bounds": {
            "min_latitude": min_lat,
            "max_latitude": max_lat,
            "min_longitude": west_lon,
            "max_longitude": east_lon,
        }
        if None not in (min_lat, max_lat, west_lon, east_lon)
        else None,
        "horizontal_resolution_m": (map_scale_km * 1000.0) if map_scale_km else None,
        "map_resolution_ppd": map_res_ppd,
        "planetary_radii_m": radii_m,
        "image_lines": int(img_obj["LINES"]) if img_obj.get("LINES", "").isdigit() else None,
        "image_samples": int(img_obj["LINE_SAMPLES"]) if img_obj.get("LINE_SAMPLES", "").isdigit() else None,
        "sample_bits": int(img_obj["SAMPLE_BITS"]) if img_obj.get("SAMPLE_BITS", "").isdigit() else None,
        "sample_type": img_obj.get("SAMPLE_TYPE"),
        "table_rows": int(tbl_obj["ROWS"]) if str(tbl_obj.get("ROWS", "")).isdigit() else None,
        "table_columns": int(tbl_obj.get("COLUMNS") or tbl_obj.get("FIELDS") or 0) or None,
        "structure_file": tbl_obj.get("^STRUCTURE"),
        "parsed_odl": parsed,
    }
