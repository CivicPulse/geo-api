"""File format parsers for GIS data import.

Supports GeoJSON, KML, and SHP files. Each parser returns a list of dicts
with uniform schema: {"properties": {...}, "geometry": {"coordinates": [lng, lat]}}.

- GeoJSON: parsed via stdlib json
- KML: parsed via stdlib xml.etree.ElementTree
- SHP: parsed via fiona with automatic CRS reprojection to EPSG:4326
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import fiona
from fiona.transform import transform_geom

# KML namespace used by OGC KML 2.2
_KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def load_geojson(path: Path) -> list[dict[str, Any]]:
    """Parse a GeoJSON file and return a list of feature dicts.

    Each feature dict has the standard GeoJSON schema:
      {"properties": {...}, "geometry": {"type": "Point", "coordinates": [lng, lat]}}

    Args:
        path: Path to a .geojson file.

    Returns:
        List of feature dicts. Features missing geometry are skipped.

    Raises:
        ValueError: If the file extension is not .geojson.
    """
    path = Path(path)
    if path.suffix.lower() != ".geojson":
        raise ValueError(f"Unsupported file extension '{path.suffix}'. Expected .geojson")

    with path.open() as f:
        data = json.load(f)

    features = []
    for feat in data.get("features", []):
        if not feat.get("geometry"):
            continue
        features.append(feat)

    return features


def load_kml(path: Path) -> list[dict[str, Any]]:
    """Parse a KML file and return a list of feature dicts with GeoJSON-like schema.

    Extracts coordinates from <kml:coordinates> elements and properties from
    <kml:SimpleData> elements within each <kml:Placemark>.

    Args:
        path: Path to a .kml file.

    Returns:
        List of feature dicts: {"properties": {...}, "geometry": {"coordinates": [lng, lat]}}.
        Placemarks missing a Point geometry are skipped.

    Raises:
        ValueError: If the file extension is not .kml.
    """
    path = Path(path)
    if path.suffix.lower() != ".kml":
        raise ValueError(f"Unsupported file extension '{path.suffix}'. Expected .kml")

    tree = ET.parse(path)
    root = tree.getroot()

    features = []
    for placemark in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        # Extract coordinates from Point/coordinates element
        coords_el = placemark.find(".//{http://www.opengis.net/kml/2.2}coordinates")
        if coords_el is None or not coords_el.text:
            continue

        # KML coordinates format: "lng,lat[,alt] ..." (space-separated tuples)
        coord_text = coords_el.text.strip().split()[0]  # first tuple
        parts = coord_text.split(",")
        if len(parts) < 2:
            continue

        try:
            lng = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue

        # Extract properties from SimpleData elements
        properties: dict[str, Any] = {}
        for simple_data in placemark.iter("{http://www.opengis.net/kml/2.2}SimpleData"):
            name = simple_data.get("name")
            if name is not None:
                properties[name] = simple_data.text or ""

        features.append({
            "properties": properties,
            "geometry": {
                "type": "Point",
                "coordinates": [lng, lat],
            },
        })

    return features


def load_shp(path: Path) -> list[dict[str, Any]]:
    """Parse a Shapefile and return a list of feature dicts with GeoJSON-like schema.

    Automatically reprojects coordinates to EPSG:4326 (WGS84) if the source
    CRS is not already WGS84.

    Args:
        path: Path to a .shp file.

    Returns:
        List of feature dicts: {"properties": {...}, "geometry": {"coordinates": [lng, lat]}}.
        Features missing geometry are skipped.

    Raises:
        ValueError: If the file extension is not .shp.
    """
    path = Path(path)
    if path.suffix.lower() != ".shp":
        raise ValueError(f"Unsupported file extension '{path.suffix}'. Expected .shp")

    features = []
    with fiona.open(path) as src:
        src_crs = src.crs
        # Determine whether reprojection is needed
        needs_reproject = _needs_reproject(src_crs)

        for feat in src:
            geom = feat.get("geometry")
            if geom is None:
                continue

            if needs_reproject:
                geom_wgs84 = transform_geom(src_crs, "EPSG:4326", geom)
            else:
                geom_wgs84 = geom

            coords = geom_wgs84.get("coordinates")
            if not coords:
                continue

            features.append({
                "properties": dict(feat.get("properties") or {}),
                "geometry": {
                    "type": geom_wgs84.get("type", "Point"),
                    "coordinates": list(coords),
                },
            })

    return features


def _needs_reproject(crs) -> bool:
    """Return True if the CRS is not EPSG:4326 (WGS84)."""
    if crs is None:
        return False
    # fiona CRS can be a dict or a CRS object
    if hasattr(crs, "to_epsg"):
        return crs.to_epsg() != 4326
    # dict-style CRS from older fiona
    if isinstance(crs, dict):
        init = crs.get("init", "")
        return "epsg:4326" not in init.lower()
    # string CRS
    return "epsg:4326" not in str(crs).lower()
