"""Filter engine for industrial areas based on proximity criteria."""

import logging
from math import cos, radians

import numpy as np
from scipy.spatial import cKDTree

from find_areas.distance import haversine, point_to_segment_distance_km
from find_areas.models import FilterConfig

logger = logging.getLogger("find_areas")


class FilterEngine:
    """Filters industrial areas based on active distance criteria.

    Supports two criteria:
    - Criterion B: Proximity to high-voltage power lines (point-to-polyline).
    - Criterion C: Proximity to water sources (point-to-point Haversine).
    """

    def __init__(self, config: FilterConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_filters(
        self,
        industrial_areas: list[dict],
        power_lines: list[dict] | None,
        water_sources: list[dict] | None,
    ) -> list[dict]:
        """Filter *industrial_areas* according to the active criteria.

        Only enabled criteria are applied.  Distance fields are added to
        each area dict **only** when the corresponding criterion is
        enabled.

        Returns:
            A (potentially smaller) list of area dicts that satisfy all
            active criteria.
        """
        logger.info("Filtering %d industrial areas...", len(industrial_areas))
        result = list(industrial_areas)

        if self.config.proximity_power_line_enabled and power_lines is not None:
            result = self._filter_by_power_lines(result, power_lines)

        if self.config.proximity_water_source_enabled and water_sources is not None:
            result = self._filter_by_water_sources(result, water_sources)

        return result

    # ------------------------------------------------------------------
    # Criterion B – power lines
    # ------------------------------------------------------------------

    def _filter_by_power_lines(
        self,
        areas: list[dict],
        power_lines: list[dict],
    ) -> list[dict]:
        tree, node_to_line = self._build_power_line_index(power_lines)
        threshold = self.config.max_distance_power_line_km
        kept: list[dict] = []

        for area in areas:
            lat = area["center"]["lat"]
            lon = area["center"]["lon"]
            dist = self._find_nearest_power_line(
                lat, lon, tree, node_to_line, power_lines,
            )
            logger.debug(
                "Area (%.4f, %.4f) -> nearest power line: %.4f km",
                lat, lon, dist,
            )
            if dist < threshold:
                area["_distance_power_line_km"] = dist
                kept.append(area)

        logger.info(
            "Power line filter: %d of %d areas within threshold",
            len(kept), len(areas),
        )
        return kept

    @staticmethod
    def _build_power_line_index(
        power_lines: list[dict],
    ) -> tuple[cKDTree, list[tuple[int, int]]]:
        """Build a cKDTree spatial index over all power-line nodes.

        Coordinates are projected using Equirectangular approximation:
        ``(radians(lat), radians(lon) * cos(radians(lat)))``.

        Returns:
            tree:
                A :class:`~scipy.spatial.cKDTree` over the projected
                coordinates.
            node_to_line:
                A list mapping each tree index to a
                ``(line_index, node_index)`` tuple.
        """
        all_points: list[list[float]] = []
        node_to_line: list[tuple[int, int]] = []

        for line_idx, line in enumerate(power_lines):
            for node_idx, node in enumerate(line["geometry"]):
                lat_rad = radians(node["lat"])
                lon_rad = radians(node["lon"])
                all_points.append([
                    lat_rad,
                    lon_rad * cos(lat_rad),
                ])
                node_to_line.append((line_idx, node_idx))

        logger.info(
            "Building power line spatial index with %d nodes...",
            len(all_points),
        )
        tree = cKDTree(np.array(all_points))
        return tree, node_to_line

    @staticmethod
    def _find_nearest_power_line(
        area_lat: float,
        area_lon: float,
        tree: cKDTree,
        node_to_line: list[tuple[int, int]],
        power_lines: list[dict],
        k: int = 10,
    ) -> float:
        """Find the minimum distance from an area centre to any power line.

        1. Query the *k* nearest nodes via the cKDTree.
        2. For each returned node check the segment **before** and
           **after** it using exact point-to-segment distance.
        3. Return the minimum distance found.
        """
        lat_rad = radians(area_lat)
        lon_rad = radians(area_lon)
        query_point = [lat_rad, lon_rad * cos(lat_rad)]

        # Clamp k to the number of points in the tree
        actual_k = min(k, tree.n)
        if actual_k == 0:
            return float("inf")

        _, indices = tree.query(query_point, k=actual_k)

        # tree.query returns a scalar when k == 1
        if np.ndim(indices) == 0:
            indices = [int(indices)]

        min_dist = float("inf")
        checked_segments: set[tuple[int, int]] = set()

        for idx in indices:
            line_idx, node_idx = node_to_line[idx]
            geometry = power_lines[line_idx]["geometry"]

            # Segment before the node
            if node_idx > 0:
                seg = (line_idx, node_idx - 1)
                if seg not in checked_segments:
                    checked_segments.add(seg)
                    dist = point_to_segment_distance_km(
                        area_lat, area_lon,
                        geometry[node_idx - 1]["lat"],
                        geometry[node_idx - 1]["lon"],
                        geometry[node_idx]["lat"],
                        geometry[node_idx]["lon"],
                    )
                    min_dist = min(min_dist, dist)

            # Segment after the node
            if node_idx < len(geometry) - 1:
                seg = (line_idx, node_idx)
                if seg not in checked_segments:
                    checked_segments.add(seg)
                    dist = point_to_segment_distance_km(
                        area_lat, area_lon,
                        geometry[node_idx]["lat"],
                        geometry[node_idx]["lon"],
                        geometry[node_idx + 1]["lat"],
                        geometry[node_idx + 1]["lon"],
                    )
                    min_dist = min(min_dist, dist)

        return min_dist

    # ------------------------------------------------------------------
    # Criterion C – water sources
    # ------------------------------------------------------------------

    def _filter_by_water_sources(
        self,
        areas: list[dict],
        water_sources: list[dict],
    ) -> list[dict]:
        threshold = self.config.max_distance_water_source_km
        kept: list[dict] = []

        for area in areas:
            lat = area["center"]["lat"]
            lon = area["center"]["lon"]
            dist, name = self._find_nearest_water_source(
                lat, lon, water_sources,
            )
            logger.debug(
                "Area (%.4f, %.4f) -> nearest water source: %.4f km (%s)",
                lat, lon, dist, name,
            )
            if dist < threshold:
                area["_distance_water_source_km"] = dist
                area["_water_source_name"] = name
                kept.append(area)

        logger.info(
            "Water source filter: %d of %d areas within threshold",
            len(kept), len(areas),
        )
        return kept

    @staticmethod
    def _find_nearest_water_source(
        area_lat: float,
        area_lon: float,
        water_sources: list[dict],
    ) -> tuple[float, str | None]:
        """Find the nearest water source using Haversine distance.

        Returns:
            ``(distance_km, name)`` where *name* may be ``None``.
        """
        min_dist = float("inf")
        nearest_name: str | None = None

        for source in water_sources:
            dist = haversine(
                area_lat, area_lon,
                source["center"]["lat"],
                source["center"]["lon"],
            )
            if dist < min_dist:
                min_dist = dist
                nearest_name = source.get("tags", {}).get("name")

        return min_dist, nearest_name
