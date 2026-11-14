"""
MARSCOPE Scientific Target Registry
Martian Surface Intelligence & Exploration System

Manages evidence-backed geological targets.
Per project rules, no targets with fabricated coordinates or conclusions are prepopulated.
"""

from typing import Dict, List, Optional
from app.schemas.target import ScienceTarget


class TargetRegistryService:
    def __init__(self):
        self._targets: Dict[str, ScienceTarget] = {}

    def register_target(self, target: ScienceTarget) -> ScienceTarget:
        """
        Register a verified scientific target backed by published provenance.
        """
        self._targets[target.target_id] = target
        return target

    def get_target(self, target_id: str) -> Optional[ScienceTarget]:
        return self._targets.get(target_id)

    def list_targets(self, classification: Optional[str] = None) -> List[ScienceTarget]:
        """
        Returns registered evidence-backed targets.
        If zero verified targets have been loaded, returns empty list.
        """
        results = list(self._targets.values())
        if classification:
            results = [t for t in results if classification.lower() in t.classification.lower()]
        return results
