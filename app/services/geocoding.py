"""
Geocoding utilities using Nominatim (OpenStreetMap).
All calls are synchronous and cached in-process for 1 hour to avoid hammering Nominatim.
"""

from __future__ import annotations

import time
import urllib.request
import urllib.parse
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Simple TTL cache; (lat_rounded, lng_rounded) → (result, timestamp)
_CACHE: dict[tuple[float, float], tuple["GeoLocation", float]] = {}
_CACHE_TTL = 3600  # 1 hour
_ROUND = 4  # ~11m precision at equator


@dataclass
class GeoLocation:
    display_name: str = ""
    road: str = ""
    suburb: str = ""
    neighbourhood: str = ""
    city: str = ""
    state_district: str = ""  
    state: str = ""
    country: str = ""
    postcode: str = ""
    # raw address dict from Nominatim for any extra fields
    raw: dict[str, Any] = field(default_factory=dict)

    def ward_guess(self) -> str:
        candidates = [
            self.raw.get("quarter"),
            self.raw.get("residential"),
            self.raw.get("borough"),
            self.state_district,
            self.suburb,
            self.neighbourhood,
            self.city,
        ]
        for c in candidates:
            if c:
                return c
        return "Unspecified"


def reverse_geocode(lat: float, lng: float) -> GeoLocation | None:
    cache_key = (round(lat, _ROUND), round(lng, _ROUND))
    if cache_key in _CACHE:
        result, ts = _CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return result

    url = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lng}&format=json&addressdetails=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "CitizenComplaintApp/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        logger.warning("Nominatim reverse-geocode failed: %s", exc)
        return None

    addr = data.get("address", {})
    geo = GeoLocation(
        display_name=data.get("display_name", ""),
        road=addr.get("road", ""),
        suburb=addr.get("suburb", ""),
        neighbourhood=addr.get("neighbourhood", ""),
        city=addr.get("city") or addr.get("town") or addr.get("village", ""),
        state_district=addr.get("state_district", ""),
        state=addr.get("state", ""),
        country=addr.get("country", ""),
        postcode=addr.get("postcode", ""),
        raw=addr,
    )

    _CACHE[cache_key] = (geo, time.time())
    return geo