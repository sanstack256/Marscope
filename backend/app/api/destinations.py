"""
MARSCOPE Destination Selection & Composition Search Endpoints
Martian Surface Intelligence & Exploration System
"""

from fastapi import APIRouter, HTTPException
from app.schemas.destination import (
    CompositionSearchRequest,
    CompositionSearchResponse,
    DestinationEvaluationResponse,
    DestinationSelectionRequest,
)
from app.services.container import destination_service

router = APIRouter(prefix="/destinations", tags=["Destination Selection"])


@router.post("/evaluate", response_model=DestinationEvaluationResponse)
async def evaluate_destination(request: DestinationSelectionRequest) -> DestinationEvaluationResponse:
    """
    Validate selected coordinates against Mars CRS conventions, check overlapping catalog products,
    and sample real elevation/slope/aspect/TRI from validated local DEMs when available.
    """
    try:
        return destination_service.evaluate_destination(request)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/search-composition", response_model=CompositionSearchResponse)
async def search_composition(request: CompositionSearchRequest) -> CompositionSearchResponse:
    """
    Contract endpoint for future mineral/element search (CRISM/ChemCam/CheMin).
    Never returns synthetic or hardcoded mineral occurrences.
    """
    return destination_service.search_composition(request.query)
