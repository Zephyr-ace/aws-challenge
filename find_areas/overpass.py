"""Overpass API client for querying OpenStreetMap data."""

from __future__ import annotations

import logging

import requests

from find_areas.exceptions import OverpassTimeoutError

logger = logging.getLogger("find_areas")

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"


class OverpassClient:
    """Client for the OpenStreetMap Overpass API.

    Provides methods to query industrial areas, power lines, and water
    sources within Germany.  All queries use a 180-second server-side
    timeout and communicate via JSON.
    """

    def __init__(self, url: str = OVERPASS_API_URL) -> None:
        self.url = url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_query(self, query: str) -> list[dict]:
        """Send an Overpass QL query and return the ``elements`` list.

        Raises
        ------
        OverpassTimeoutError
            If the Overpass server signals a timeout (HTTP 429 or the
            ``remark`` field contains "timeout") or the HTTP request
            itself times out.
        ConnectionError
            If a network-level error occurs.
        """
        logger.info("Overpass request: %s", self.url)
        logger.debug("Overpass query:\n%s", query)

        try:
            response = requests.post(
                self.url,
                data={"data": query},
                timeout=200,  # slightly above the 180s server timeout
            )
        except requests.exceptions.Timeout as exc:
            raise OverpassTimeoutError(
                f"Overpass API request timed out: {exc}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Failed to connect to Overpass API: {exc}"
            ) from exc

        # The Overpass API returns HTTP 429 (or 200 with a remark) on timeout
        if response.status_code == 429:
            raise OverpassTimeoutError(
                "Overpass API returned HTTP 429 (too many requests / timeout)"
            )

        response.raise_for_status()

        data = response.json()

        # Some timeout errors come back as HTTP 200 with a remark field
        remark = data.get("remark", "")
        if "timeout" in remark.lower():
            raise OverpassTimeoutError(f"Overpass API timeout: {remark}")

        elements = data.get("elements", [])
        logger.debug("Overpass response: %d elements, %d bytes", len(elements), len(response.content))
        return elements

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
