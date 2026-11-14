"""
MARSCOPE Base Archive Source Adapter
Martian Surface Intelligence & Exploration System
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.schemas.dataset import Dataset, GeographicCoverage


class SourceAdapter(ABC):
    """
    Abstract adapter for official NASA / ESA planetary archives.
    """
    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        pass

    @abstractmethod
    def discover_products(self, target_region: Optional[Dict[str, float]] = None) -> List[Dataset]:
        """
        Query archive or catalog for verified products.
        """
        pass

    @staticmethod
    def calculate_spatial_overlap(coverage: GeographicCoverage, target_bounds: Dict[str, float]) -> float:
        """
        Calculate intersection area ratio [0.0, 1.0] between dataset footprint and target bounding box.
        target_bounds: {"min_lat": float, "max_lat": float, "min_lon": float, "max_lon": float}
        """
        t_min_lat = target_bounds["min_lat"]
        t_max_lat = target_bounds["max_lat"]
        t_min_lon = target_bounds["min_lon"]
        t_max_lon = target_bounds["max_lon"]

        inter_min_lat = max(coverage.min_latitude, t_min_lat)
        inter_max_lat = min(coverage.max_latitude, t_max_lat)
        inter_min_lon = max(coverage.min_longitude, t_min_lon)
        inter_max_lon = min(coverage.max_longitude, t_max_lon)

        if inter_min_lat >= inter_max_lat or inter_min_lon >= inter_max_lon:
            return 0.0

        inter_area = (inter_max_lat - inter_min_lat) * (inter_max_lon - inter_min_lon)
        target_area = (t_max_lat - t_min_lat) * (t_max_lon - t_min_lon)

        if target_area <= 0:
            return 0.0

        return min(1.0, max(0.0, inter_area / target_area))
