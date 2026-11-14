"""
NASA Mars 2020 Perseverance Raw Images Gallery Source Adapter
Strictly isolated to Jezero Crater mission imagery — never mixed into Gale Crater routes or targets.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.ingestion.http_client import create_async_http_client

PERSEVERANCE_RSS_URL = "https://mars.nasa.gov/rss/api/"


class PerseveranceGalleryService:
    """
    Live client for the official NASA Mars 2020 Perseverance Raw Images Gallery API.
    Enforces strict separation from Gale Crater / Curiosity navigation and target datasets.
    """

    @staticmethod
    async def fetch_raw_images(
        *,
        sol: Optional[int] = None,
        camera: Optional[str] = None,
        limit: int = 12,
        page: int = 0,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit), 50))
        safe_page = max(0, int(page))
        params: Dict[str, Any] = {
            "feed": "raw_images",
            "category": "mars2020",
            "feedtype": "json",
            "ver": "1.2",
            "num": safe_limit,
            "page": safe_page,
        }
        if sol is not None:
            params["condition_1"] = f"{int(sol)}:sol:in"
        if camera and camera.strip():
            params["search"] = camera.strip().upper()

        retrieved_at = datetime.now(timezone.utc).isoformat()
        factory = client_factory or (lambda: create_async_http_client(timeout_seconds=10.0))

        try:
            async with factory() as client:
                resp = await client.get(PERSEVERANCE_RSS_URL, params=params)
                if resp.status_code != 200:
                    return {
                        "status": "remote_error",
                        "mission": "Mars 2020 Perseverance",
                        "site": "Jezero Crater",
                        "isolated_from_gale_planning": True,
                        "isolation_note": "Jezero Crater mission feed only; strictly isolated from Gale Crater targets and route computation.",
                        "source_url": PERSEVERANCE_RSS_URL,
                        "retrieved_at_utc": retrieved_at,
                        "total_results": 0,
                        "images": [],
                        "error": f"NASA Mars 2020 Raw Images RSS returned HTTP {resp.status_code}.",
                    }
                payload = resp.json()
        except Exception as exc:
            return {
                "status": "remote_unavailable",
                "mission": "Mars 2020 Perseverance",
                "site": "Jezero Crater",
                "isolated_from_gale_planning": True,
                "isolation_note": "Jezero Crater mission feed only; strictly isolated from Gale Crater targets and route computation.",
                "source_url": PERSEVERANCE_RSS_URL,
                "retrieved_at_utc": retrieved_at,
                "total_results": 0,
                "images": [],
                "error": f"Live Perseverance feed unreachable: {exc}",
            }

        raw_images = payload.get("images") or []
        records: List[Dict[str, Any]] = []
        for item in raw_images[:safe_limit]:
            cam_info = item.get("camera") or {}
            img_files = item.get("image_files") or {}
            records.append(
                {
                    "imageid": item.get("imageid"),
                    "sol": item.get("sol"),
                    "mission": "Mars 2020 Perseverance",
                    "site": "Jezero Crater",
                    "isolated_from_gale_planning": True,
                    "camera_instrument": cam_info.get("instrument"),
                    "camera_filter": cam_info.get("filter_name"),
                    "title": item.get("title"),
                    "caption": item.get("caption"),
                    "date_taken_utc": item.get("date_taken_utc"),
                    "date_taken_mars": item.get("date_taken_mars"),
                    "sample_type": item.get("sample_type"),
                    "attitude": item.get("attitude"),
                    "image_url_medium": img_files.get("medium"),
                    "image_url_large": img_files.get("large"),
                    "image_url_full_res": img_files.get("full_res"),
                    "credit": item.get("credit") or "NASA/JPL-Caltech",
                }
            )

        return {
            "status": "available",
            "mission": "Mars 2020 Perseverance",
            "site": "Jezero Crater",
            "isolated_from_gale_planning": True,
            "isolation_note": (
                "Perseverance imagery belongs exclusively to Jezero Crater (~18.38N, 77.58E) "
                "and is strictly isolated from Gale Crater (-4.6S, 137.4E) routes and targets."
            ),
            "source_url": PERSEVERANCE_RSS_URL,
            "retrieved_at_utc": retrieved_at,
            "total_results": int(payload.get("total_results") or len(records)),
            "page": safe_page,
            "per_page": safe_limit,
            "images": records,
        }
