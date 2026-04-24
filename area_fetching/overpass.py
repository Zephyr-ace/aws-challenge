"""Overpass API client for querying OpenStreetMap data."""

from __future__ import annotations

import logging

import time

import requests

from area_fetching.exceptions import OverpassTimeoutError

logger = logging.getLogger("find_areas")

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]


class OverpassClient:
    """Client for the OpenStreetMap Overpass API.

    Provides methods to query industrial areas, power lines, and water
    sources within Germany.  All queries use a 180-second server-side
    timeout and communicate via JSON.
    """

    def __init__(self, url: str | None = None) -> None:
        self.url = url or OVERPASS_ENDPOINTS[0]
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "DataCenterSiteFinder/1.0 (https://github.com/datacenter-site-finder)",
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_query(self, query: str) -> list[dict]:
        """Send an Overpass QL query and return the ``elements`` list.

        Tries multiple Overpass endpoints with retries on transient errors.
        """
        endpoints = [self.url] + [e for e in OVERPASS_ENDPOINTS if e != self.url]
        last_exc: Exception | None = None

        for endpoint in endpoints:
            for attempt in range(1):
                logger.info("Overpass request: %s (attempt %d)", endpoint, attempt + 1)
                logger.debug("Overpass query:\n%s", query)
                try:
                    response = self._session.post(
                        endpoint,
                        data={"data": query},
                        timeout=200,
                    )
                except requests.exceptions.Timeout as exc:
                    last_exc = OverpassTimeoutError(f"Overpass API request timed out: {exc}")
                    continue
                except requests.exceptions.ConnectionError as exc:
                    last_exc = ConnectionError(f"Failed to connect to Overpass API: {exc}")
                    continue

                if response.status_code == 429:
                    last_exc = OverpassTimeoutError("Overpass API returned HTTP 429")
                    time.sleep(5)
                    continue

                if response.status_code in (406, 500, 502, 503, 504):
                    last_exc = requests.exceptions.HTTPError(
                        f"Overpass returned {response.status_code}", response=response
                    )
                    time.sleep(10)
                    continue

                response.raise_for_status()
                data = response.json()

                remark = data.get("remark", "")
                if "timeout" in remark.lower():
                    last_exc = OverpassTimeoutError(f"Overpass API timeout: {remark}")
                    continue

                elements = data.get("elements", [])
                logger.debug("Overpass response: %d elements, %d bytes", len(elements), len(response.content))
                return elements

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def query_industrial_areas(self) -> list[dict]:
        """Query all industrial areas in Germany.

        Returns a list of dicts, each with ``"center"`` (lat/lon),
        ``"tags"``, ``"type"``, and ``"id"`` keys.

        Overpass query uses ``out center tags`` so that each way/relation
        is returned with its centroid and tag set.
        """
        query = """\
[out:json][timeout:180];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  way["landuse"="industrial"](area.de);
  relation["landuse"="industrial"](area.de);
);
out center tags;"""
        elements = self._execute_query(query)
        return elements

    def query_power_lines(self) -> list[dict]:
        """Query high-voltage power lines (110 kV / 220 kV / 380 kV) in Germany.

        Returns a list of dicts, each with ``"geometry"`` (list of
        lat/lon nodes), ``"tags"``, ``"type"``, and ``"id"`` keys.

        Overpass query uses ``out geom`` so that the full node geometry
        of each way is included in the response.
        """
        query = """\
[out:json][timeout:180];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  way["power"="line"]["voltage"~"110000|220000|380000"](area.de);
);
out geom;"""
        elements = self._execute_query(query)
        return elements

    def query_substations(self) -> list[dict]:
        """Query high-voltage transmission substations (110 kV+) in Germany.

        Returns a list of dicts, each with ``"center"`` (lat/lon),
        ``"tags"``, ``"type"``, and ``"id"`` keys.

        Targets substations tagged as ``substation=transmission`` in OSM,
        which represent the grid nodes relevant for large-consumer
        connections (data centres, heavy industry).
        """
        query = """\
[out:json][timeout:180];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  node["power"="substation"]["substation"="transmission"](area.de);
  way["power"="substation"]["substation"="transmission"](area.de);
  relation["power"="substation"]["substation"="transmission"](area.de);
);
out center tags;"""
        elements = self._execute_query(query)
        return elements

    def query_water_sources(self) -> list[dict]:
        """Query water sources (rivers, canals, lakes) in Germany.

        Returns a list of dicts, each with ``"center"`` (lat/lon),
        ``"tags"``, ``"type"``, and ``"id"`` keys.

        Overpass query uses ``out center tags`` so that each element is
        returned with its centroid and tag set.
        """
        query = """\
[out:json][timeout:180];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  way["waterway"~"river|canal"](area.de);
  way["natural"="water"](area.de);
  relation["natural"="water"](area.de);
);
out center tags;"""
        elements = self._execute_query(query)
        return elements
