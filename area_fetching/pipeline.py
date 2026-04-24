"""Main pipeline for the find_areas application."""

from __future__ import annotations

import logging

from area_fetching.config import load_config
from area_fetching.enricher import MetadataEnricher
from area_fetching.filter_engine import FilterEngine
from area_fetching.llm_helper import LLMHelper
from area_fetching.models import AreaResult
from area_fetching.overpass import OverpassClient
from area_fetching.web_research_agent import WebResearchAgent

logger = logging.getLogger("find_areas")


def find_areas(config_path: str) -> list[AreaResult]:
    """Find potential data-centre sites in German industrial areas.

    Pipeline steps:
    1. Load configuration from *config_path*.
    2. Query industrial areas from OpenStreetMap via the Overpass API.
    3. Run LLM-driven web research for each industrial area.
    4. Optionally query power lines (Criterion B) and water sources
       (Criterion C).
    5. Apply distance filters.
    6. Enrich metadata and return the final result list.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        A list of :class:`AreaResult` typed dicts.
    """
    logger.info("Starting find_areas pipeline...")

    # 1. Load configuration
    config = load_config(config_path)

    # 2. Query industrial areas from OSM
    client = OverpassClient()
    industrial_areas = client.query_industrial_areas()
    logger.info("Found %d industrial areas from OSM", len(industrial_areas))

    # 3. Web research for each industrial area
    llm = LLMHelper(config.llm)
    agent = WebResearchAgent(llm)

    logger.info("Starting web research for %d areas...", len(industrial_areas))
    for area in industrial_areas:
        result = agent.research_area(
            lat=area["center"]["lat"],
            lon=area["center"]["lon"],
            osm_tags=area.get("tags"),
        )
        area["web_research"] = result
    logger.info("Web research complete")

    # 4. Optionally query infrastructure data
    power_lines: list[dict] | None = None
    water_sources: list[dict] | None = None
    substations: list[dict] | None = None

    if config.filter.proximity_power_line_enabled:
        logger.info("Querying power lines...")
        power_lines = client.query_power_lines()

    if config.filter.proximity_water_source_enabled:
        logger.info("Querying water sources...")
        water_sources = client.query_water_sources()

    if config.filter.proximity_substation_enabled:
        logger.info("Querying transmission substations...")
        substations = client.query_substations()
        logger.info("Found %d transmission substations", len(substations))

    # 5. Apply filters
    engine = FilterEngine(config.filter)
    filtered = engine.apply_filters(industrial_areas, power_lines, water_sources, substations)

    # 6. Enrich metadata
    enricher = MetadataEnricher()
    results = enricher.enrich(filtered, power_lines, water_sources, config.filter)

    logger.info("Pipeline complete: %d results", len(results))
    return results
