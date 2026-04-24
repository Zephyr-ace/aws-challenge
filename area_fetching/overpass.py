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
        """Send query to Overpass servers, trying multiple endpoints.

        Uses a fresh session per call for thread safety.
        """
        endpoints = [self.url] + [e for e in OVERPASS_ENDPOINTS if e != self.url]
        last_exc: Exception | None = None

        for endpoint in endpoints:
            logger.info("Overpass request: %s", endpoint)
            logger.debug("Overpass query:\n%s", query)
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "User-Agent": "DataCenterSiteFinder/1.0",
                        "Accept": "application/json",
                    },
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

    def _chunked_query(
        self,
        query_builder: Callable[[str], str],
        label: str,
        rows: int = 4,
        cols: int = 3,
        progress_cb: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """Run a query across bbox chunks in parallel, dedup, and merge.

        Chunks are executed concurrently (up to 3 workers) to speed up
        the initial fetch.  Each chunk is individually cached so that
        subsequent runs skip already-fetched tiles.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        boxes = self._make_bbox_grid(rows, cols)
        lock = threading.Lock()
        seen_ids: set[int] = set()
        all_elements: list[dict] = []

        def _fetch_chunk(idx: int, bbox_tuple: tuple[float, float, float, float]) -> list[dict]:
            s, w, n, e = bbox_tuple
            bbox = f"({s},{w},{n},{e})"
            query = query_builder(bbox)
            logger.info("%s chunk %d/%d  bbox=%s", label, idx + 1, len(boxes), bbox)
            try:
                return self._execute_query(query)
            except Exception:
                logger.warning("%s chunk %d failed, skipping", label, idx + 1)
                return []

        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {
                pool.submit(_fetch_chunk, i, box): i
                for i, box in enumerate(boxes)
            }
            for fut in as_completed(futs):
                elements = fut.result()
                with lock:
                    for el in elements:
                        eid = el.get("id")
                        if eid and eid not in seen_ids:
                            seen_ids.add(eid)
                            all_elements.append(el)
                if progress_cb:
                    progress_cb(1)

        logger.info("%s: %d total elements from %d chunks", label, len(all_elements), len(boxes))
        return all_elements

    # ------------------------------------------------------------------
    # Public query methods (chunked)
    # ------------------------------------------------------------------

    def query_industrial_areas(
        self,
        progress_cb: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """Query industrial areas in Germany using bbox chunks."""
        def build(bbox: str) -> str:
            return (
                f"[out:json][timeout:90];\n"
                f"(\n"
                f"  way[\"landuse\"=\"industrial\"]{bbox};\n"
                f"  relation[\"landuse\"=\"industrial\"]{bbox};\n"
                f");\n"
                f"out bb center tags;"
            )
        return self._chunked_query(build, "Industrial areas", progress_cb=progress_cb)

    def query_power_lines(
        self,
        progress_cb: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """Query high-voltage power lines in Germany using bbox chunks."""
        def build(bbox: str) -> str:
            return (
                f"[out:json][timeout:90];\n"
                f"(\n"
                f"  way[\"power\"=\"line\"][\"voltage\"~\"110000|220000|380000\"]{bbox};\n"
                f");\n"
                f"out geom;"
            )
        return self._chunked_query(build, "Power lines", progress_cb=progress_cb)

    def query_substations(
        self,
        progress_cb: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """Query transmission substations in Germany using bbox chunks."""
        def build(bbox: str) -> str:
            return (
                f"[out:json][timeout:90];\n"
                f"(\n"
                f"  node[\"power\"=\"substation\"][\"substation\"=\"transmission\"]{bbox};\n"
                f"  way[\"power\"=\"substation\"][\"substation\"=\"transmission\"]{bbox};\n"
                f"  relation[\"power\"=\"substation\"][\"substation\"=\"transmission\"]{bbox};\n"
                f");\n"
                f"out center tags;"
            )
        return self._chunked_query(build, "Substations", progress_cb=progress_cb)

    def query_water_sources(
        self,
        progress_cb: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """Query water sources in Germany using bbox chunks."""
        def build(bbox: str) -> str:
            return (
                f"[out:json][timeout:90];\n"
                f"(\n"
                f"  way[\"waterway\"~\"river|canal\"]{bbox};\n"
                f"  way[\"natural\"=\"water\"]{bbox};\n"
                f"  relation[\"natural\"=\"water\"]{bbox};\n"
                f");\n"
                f"out center tags;"
            )
        return self._chunked_query(build, "Water sources", progress_cb=progress_cb)
