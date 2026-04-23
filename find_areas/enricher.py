"""Metadata enrichment for filtered industrial areas."""

import logging

from find_areas.models import AreaResult, FilterConfig, WebResearchResult

logger = logging.getLogger("find_areas")


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

        Args:
            filtered_areas: Areas that passed the filter engine.
            power_lines: Power-line data (unused directly, kept for API
                symmetry with the pipeline).
            water_sources: Water-source data (unused directly, kept for
                API symmetry with the pipeline).
            config: The active filter configuration.

        Returns:
            A list of :class:`AreaResult` typed dicts.
        """
        logger.info("Enriching %d areas with metadata...", len(filtered_areas))

        results: list[AreaResult] = []
        for area in filtered_areas:
            logger.debug(
                "Enriching area at (%.4f, %.4f)",
                area["center"]["lat"],
                area["center"]["lon"],
            )

            web_research: WebResearchResult = area.get(
                "web_research", WebResearchResult()
            )

            # Determine area_sqm from bounds, tags, or default
            bounds = area.get("bounds")
            if bounds is not None:
                area_sqm = float(bounds)
            else:
                area_sqm_raw = area.get("tags", {}).get("area")
                area_sqm = float(area_sqm_raw) if area_sqm_raw is not None else 0.0

            # Determine industrial area name
            industrial_area_name = (
                web_research.area_name
                or area.get("tags", {}).get("name")
            )

            result: AreaResult = {
                "latitude": area["center"]["lat"],
                "longitude": area["center"]["lon"],
                "area_sqm": area_sqm,
                "industrial_area_name": industrial_area_name,
                "has_plots_for_sale": web_research.has_plots_for_sale,
                "plot_sizes_sqm": web_research.plot_sizes_sqm,
                "research_confidence": web_research.confidence,
                "research_sources": web_research.sources,
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

            results.append(result)

        return results
