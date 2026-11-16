"""
Landing-Site Registration, Catalog-Backed Mars Gazetteer Search & Algorithmic 3D DEM Perimeter Endpoints.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    AuthContext,
    load_mission_membership,
    require_auth,
    require_mission_roles,
)
from app.schemas.mission_collab import (
    ComputePerimeterRequest,
    GazetteerSiteRecord,
    LandingSiteBundleResponse,
    LandingSiteCoverageDiscoveryResponse,
    RegisterLandingSiteRequest,
)
from app.services.container import landing_site_service

router = APIRouter(tags=["Landing-Site Intelligence & 3D Perimeter"])


@router.get("/missions/gazetteer/search", response_model=List[GazetteerSiteRecord])
def search_mars_gazetteer(
    q: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(require_auth),
) -> List[GazetteerSiteRecord]:
    _ = auth
    return landing_site_service.search_gazetteer(q)


@router.get(
    "/missions/landing-site/discover-coverage",
    response_model=LandingSiteCoverageDiscoveryResponse,
)
def discover_landing_site_coverage(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=360.0),
    auth: AuthContext = Depends(require_auth),
) -> LandingSiteCoverageDiscoveryResponse:
    _ = auth
    return landing_site_service.discover_coverage(lat, lon)


@router.get("/missions/{mission_id}/landing-site", response_model=LandingSiteBundleResponse)
def get_mission_landing_site(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> LandingSiteBundleResponse:
    load_mission_membership(mission_id, auth)
    return landing_site_service.get_bundle(mission_id)


@router.put("/missions/{mission_id}/landing-site", response_model=LandingSiteBundleResponse)
def register_mission_landing_site(
    mission_id: str,
    payload: RegisterLandingSiteRequest,
    auth: AuthContext = Depends(require_auth),
) -> LandingSiteBundleResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return landing_site_service.register_landing_site(mission_id, auth.astronaut_id, payload)


@router.post("/missions/{mission_id}/landing-site/perimeter", response_model=LandingSiteBundleResponse)
def evaluate_landing_site_perimeter(
    mission_id: str,
    payload: ComputePerimeterRequest,
    auth: AuthContext = Depends(require_auth),
) -> LandingSiteBundleResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return landing_site_service.compute_perimeter(mission_id, auth.astronaut_id, payload)


@router.post(
    "/missions/{mission_id}/landing-site/perimeter/{perimeter_id}/approve",
    response_model=LandingSiteBundleResponse,
)
def approve_landing_site_perimeter(
    mission_id: str,
    perimeter_id: str,
    auth: AuthContext = Depends(require_auth),
) -> LandingSiteBundleResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return landing_site_service.approve_perimeter(mission_id, perimeter_id, auth.astronaut_id)
