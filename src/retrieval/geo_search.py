"""Vectorized Haversine distance, in kilometers."""
from __future__ import annotations

EARTH_RADIUS_KM = 6371.0088


def parse_location(location):
    import math
    """Accept [lat, lon] or {'latitude': ..., 'longitude': ...} (also lat/lon)."""
    if isinstance(location, (tuple, list)) and len(location) == 2:
        lat, lon = location
    elif isinstance(location, dict):
        lat = location.get('latitude', location.get('lat'))
        lon = location.get('longitude', location.get('lon', location.get('lng')))
    else:
        raise ValueError('location must be [latitude, longitude] or a lat/lon dict')
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise ValueError('location latitude/longitude must be numbers') from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid location coordinates')
    return lat, lon


def haversine_km(lat, lon, latitudes, longitudes):
    """Return a Series aligned with the input; missing coordinates => NaN."""
    import numpy as np
    import pandas as pd
    latitudes = pd.to_numeric(latitudes, errors='coerce')
    longitudes = pd.to_numeric(longitudes, errors='coerce')
    phi1, phi2 = np.radians(lat), np.radians(latitudes)
    dphi = np.radians(latitudes - lat)
    dlambda = np.radians(longitudes - lon)
    a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2)**2
    a = np.clip(a, 0, 1)
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


def restaurants_with_distance(restaurants: pd.DataFrame, location) -> pd.DataFrame:
    lat, lon = parse_location(location)
    result = restaurants.copy()
    result['distance_km'] = haversine_km(lat, lon, result['latitude'], result['longitude'])
    return result
