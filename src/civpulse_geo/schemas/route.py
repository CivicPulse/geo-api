"""Pydantic response schemas for /route endpoint (ROUTE-01, ROUTE-02, ROUTE-03)."""
from pydantic import BaseModel


class Maneuver(BaseModel):
    """A single turn-by-turn maneuver within a route leg."""

    instruction: str
    distance_meters: float
    duration_seconds: float
    type: int


class RouteResponse(BaseModel):
    """Structured route response (ROUTE-03)."""

    mode: str
    polyline: str
    duration_seconds: float
    distance_meters: float
    maneuvers: list[Maneuver]
    raw_valhalla: dict
