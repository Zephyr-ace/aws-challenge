"""Overpass API client with bbox-chunked queries and disk caching."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable

import requests

from area_fetching.exceptions import OverpassTimeoutError

logger = logging.getLogger("find_areas")

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]

# Germany approximate bounding box
_DE_SOUTH = 47.27
_DE_NORTH = 55.06
_DE_WEST = 5.87
_DE_EAST = 15.04

# Default cache directory
_CACHE_DIR = Path(".overpass_cache")


class OverpassClient:
    """Client for the OpenStreetMap Overpass API.

    Supports splitting large Germany-wide queries into smaller
    bounding-box chunks that are individually cached to disk as JSON.
    """

    def __init__(
        self,
        url: str | None = None,
        cache_dir: str | Path = _CACHE_DIR,
        cache_enabled: bool = True,
    ) -> None:
        self.url = url or OVERPASS_ENDPOINTS[0]
        self._cache_dir = Path(cache_dir)
        self._cache_enabled = cache_enabled
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "DataCenterSiteFinder/1.0",
            "Accept": "application/json",
        })
        if self._cache_enabled:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, query: str) -> str:
        return hashlib.sha256(query.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _load_cache(self, key: str) -> list[dict] | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, key: str, elements: list[dict]) -> None:
        try:
            with open(self._cache_path(key), "w", encoding="utf-8") as f:
                json.dump(elements, f)
        except OSError:
            logger.warning("Failed to write cache file for key %s", key)

    # ------------------------------------------------------------------
    # Low-level query execution
    # ------------------------------------------------------------------

    def _execute_query(self, query: str) -> list[dict]:
        """Send an Overpass QL query and return the ``elements`` list."""
        if self._cache_enabled:
            key = self._cache_key(query)
            cached = self._load_cache(key)
            if cached is not None:
                logger.debug("Cache hit for query (key=%s, %d elements)", key, len(cached))
                return cached

        elements = self._execute_query_remote(query)

        if self._cache_enabled:
            self._save_cache(self._cache_key(query), elements)

        return elements

    def _execute_query_remote(self, query: str) -> list[dict]:
        """Send query to Overpass servers, trying multiple endpoints."""
        endpoints = [self.url] + [e for e in OVERPASS_ENDPOINTS if e != self.url]
        last_exc: Exception | None = None

        for endpoint in endpoints:
            logger.info("Overpass request: %s", endpoint)
            logger.debug("Overpass query:\n%s", query)
            try:
                response = self._session.post(
                    endpoint,
                    data={"data": query},
                    timeout=200,
                )
            except requests.exceptions.Timeout as exc:
                last_exc = OverpassTimeoutError(f"Overpass API timed out: {exc}")
                continue
            except requests.exceptions.ConnectionError as exc:
                last_exc = ConnectionError(f"Connection failed: {exc}")
                continue

            if response.status_code == 429:
                last_exc = OverpassTimeoutError("HTTP 429")
                time.sleep(5)
                continue

            if response.status_code in (406, 500, 502, 503, 504):
                last_exc = requests.exceptions.HTTPError(
                    f"Overpass returned {response.status_code}",
                    response=response,
                )
                time.sleep(10)
                continue

            response.raise_for_status()
            data = response.json()

            remark = data.get("remark", "")
            if "timeout" in remark.lower():
                last_exc = OverpassTimeoutError(f"Server timeout: {remark}")
                continue

            elements = data.get("elements", [])
            logger.debug("Overpass response: %d elements", len(elements))
            return elements

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Bbox-chunked queries
    # ------------------------------------------------------------------

    @staticmethod
    def _make_bbox_grid(
        rows: int = 4,
        cols: int = 3,
    ) -> list[tuple[float, float, float, float]]:
        """Split Germany's bounding box into a grid of smaller boxes.

        Returns a list of ``(south, west, north, east)`` tuples.
        """
        lat_step = (_DE_NORTH - _DE_SOUTH) / rows
        lon_step = (_DE_EAST - _DE_WEST) / cols
        boxes: list[tuple[float, float, float, float]] = []
        for r in range(rows):
            for c in range(cols):
                s = _DE_SOUTH + r * lat_step
                n = s + lat_step
                w = _DE_WEST + c * lon_step
                e = w + lon_step
                boxes.append((s, w, n, e))
        return boxes
