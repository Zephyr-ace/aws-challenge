"""Metadata enrichment for filtered industrial areas."""

import logging
from math import cos, radians

from area_fetching.models import AreaResult, FilterConfig

logger = logging.getLogger("find_areas")


def _bbox_area_sqm(bounds: dict) -> float:
    """Approximate area in m² from an Overpass bounding box.

    Uses Equirectangular projection: width adjusted by cos(mid_lat).
    """
    min_lat = bounds.get("minlat", 0.0)
    max_lat = bounds.get("maxlat", 0.0)
    min_lon = bounds.get("minlon", 0.0)
    max_lon = bounds.get("maxlon", 0.0)

    mid_lat_rad = radians((min_lat + max_lat) / 2)
    # 1 degree latitude ≈ 111,320 m
    height_m = (max_lat - min_lat) * 111_320
    width_m = (max_lon - min_lon) * 111_320 * cos(mid_lat_rad)
    return abs(height_m * width_m)


class MetadataEnricher:
    """Enriches filtered areas with metadata to produce final AreaResult dicts."""

    def enrich(
        self,
        filtered_areas: list[dict],
        power_lines: list[dict] | None,
        water_sources: list[dict] | None,
        config: FilterConfig,
    ) -> list[AreaResult]:
        """Build :class:`AreaResult` dicts from *filtered_areas*.

        Required fields are always present.  Conditional fields
        (``distance_power_line_km``, ``water_source_name``,
        ``distance_water_source_km``) are only included when the
        corresponding criterion is active in *config*.
        """
        logger.info("Enriching %d areas with metadata...", len(filtered_areas))

        results: list[AreaResult] = []
        for area in filtered_areas:
            logger.debug(
                "Enriching area at (%.4f, %.4f)",
                area["center"]["lat"],
                area["center"]["lon"],
            )

            # Determine area_sqm from bounding box or tags
            bounds = area.get("bounds")
            if bounds is not None and isinstance(bounds, dict):
                area_sqm = _bbox_area_sqm(bounds)
            else:
                area_sqm_raw = area.get("tags", {}).get("area")
                try:
                    area_sqm = float(area_sqm_raw) if area_sqm_raw is not None else 0.0
                except (ValueError, TypeError):
                    area_sqm = 0.0

            # Determine industrial area name from OSM tags
            industrial_area_name = area.get("tags", {}).get("name")

            result: AreaResult = {
                "latitude": area["center"]["lat"],
                "longitude": area["center"]["lon"],
                "area_sqm": area_sqm,
                "industrial_area_name": industrial_area_name,
            }

            # Conditional fields
            if config.proximity_power_line_enabled:
                result["distance_power_line_km"] = area.get(
                    "_distance_power_line_km", 0.0
                )

            if config.proximity_water_source_enabled:
                result["water_source_name"] = area.get("_water_source_name")
                result["distance_water_source_km"] = area.get(
                    "_distance_water_source_km", 0.0
                )

            if config.proximity_substation_enabled:
                result["nearest_substation_name"] = area.get("_substation_name")
                result["nearest_substation_voltage"] = area.get("_substation_voltage")
                result["nearest_substation_operator"] = area.get("_substation_operator")
                result["distance_substation_km"] = area.get(
                    "_distance_substation_km", 0.0
                )

            results.append(result)

        return results
