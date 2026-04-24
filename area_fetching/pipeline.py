"""Main pipeline for the find_areas application.

Optimised execution order:
1. Load config.
2. Fetch all Overpass data in parallel (chunked + cached).
3. Apply proximity filters (cheap, no network).
4. Spatially sample down to ``max_locations``.
5. Run LLM web research only on the surviving areas (parallel).
6. Enrich and return.
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import cos, radians

import numpy as np

from area_fetching.config import load_config
from area_fetching.enricher import MetadataEnricher
from area_fetching.filter_engine import FilterEngine
from area_fetching.llm_helper import LLMHelper
from area_fetching.models import AppConfig, AreaResult
from area_fetching.overpass import OverpassClient
from area_fetching.progress import ProgressTracker
from area_fetching.web_research_agent import WebResearchAgent

logger = logging.getLogger("find_areas")


# ------------------------------------------------------------------
# Spatial sampling
# ------------------------------------------------------------------

def _spatially_sample(areas: list[dict], n: int) -> list[dict]:
    """Select up to *n* areas spread evenly across Germany.

    Uses greedy farthest-point sampling on an Equirectangular
    projection so the selected subset has good spatial coverage.
    """
    if len(areas) <= n:
        return list(areas)

    coords = np.empty((len(areas), 2), dtype=np.float64)
    for i, a in enumerate(areas):
        lat = a["center"]["lat"]
        lon = a["center"]["lon"]
        coords[i, 0] = radians(lat) * 6371.0
        coords[i, 1] = radians(lon) * cos(radians(lat)) * 6371.0

    selected: list[int] = []
    centroid = coords.mean(axis=0)
    first = int(np.argmin(np.sum((coords - centroid) ** 2, axis=1)))
    selected.append(first)

    min_dist = np.sum((coords - coords[first]) ** 2, axis=1)
    for _ in range(n - 1):
        nxt = int(np.argmax(min_dist))
        selected.append(nxt)
        min_dist = np.minimum(min_dist, np.sum((coords - coords[nxt]) ** 2, axis=1))

    logger.info("Spatial sampling: %d → %d areas", len(areas), len(selected))
    return [areas[i] for i in selected]


# ------------------------------------------------------------------
# Phase 1 – Overpass fetching (parallel, chunked, cached)
# ------------------------------------------------------------------

def _count_overpass_chunks(config: AppConfig) -> int:
    """Count how many Overpass chunk requests will be made."""
    grid = 4 * 3  # 12 chunks per query type
    n = grid  # industrial areas always fetched
    if config.filter.proximity_power_line_enabled:
        n += grid
    if config.filter.proximity_water_source_enabled:
        n += grid
    if config.filter.proximity_substation_enabled:
        n += grid
    return n


def _fetch_overpass_data(
    client: OverpassClient,
    config: AppConfig,
) -> tuple[list[dict], list[dict] | None, list[dict] | None, list[dict] | None]:
    """Fetch all required Overpass data with a shared progress bar.

    Runs the different query types in parallel threads (one thread per
    query type).  Each query type is internally chunked into bbox tiles
    that are individually cached.
    """
    total_chunks = _count_overpass_chunks(config)
    progress = ProgressTracker("Overpass fetch", total_chunks)

    industrial: list[dict] = []
    power_lines: list[dict] | None = None
    water_sources: list[dict] | None = None
    substations: list[dict] | None = None

    def _fetch_industrial() -> list[dict]:
        return client.query_industrial_areas(progress_cb=progress.advance)

    def _fetch_power_lines() -> list[dict]:
        return client.query_power_lines(progress_cb=progress.advance)

    def _fetch_water() -> list[dict]:
        return client.query_water_sources(progress_cb=progress.advance)

    def _fetch_substations() -> list[dict]:
        return client.query_substations(progress_cb=progress.advance)

    futures_map: dict[str, any] = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures_map["industrial"] = pool.submit(_fetch_industrial)

        if config.filter.proximity_power_line_enabled:
            futures_map["power_lines"] = pool.submit(_fetch_power_lines)
        if config.filter.proximity_water_source_enabled:
            futures_map["water"] = pool.submit(_fetch_water)
        if config.filter.proximity_substation_enabled:
            futures_map["substations"] = pool.submit(_fetch_substations)

        for name, fut in futures_map.items():
            try:
                result = fut.result()
            except Exception:
                logger.exception("Overpass fetch failed for %s", name)
                result = []

            if name == "industrial":
                industrial = result
            elif name == "power_lines":
                power_lines = result
            elif name == "water":
                water_sources = result
            elif name == "substations":
                substations = result

    progress.finish()
    return industrial, power_lines, water_sources, substations


# ------------------------------------------------------------------
# Phase 2 – LLM web research (parallel)
# ------------------------------------------------------------------

def _run_web_research(
    areas: list[dict],
    config: AppConfig,
) -> None:
    """Run LLM web research on *areas* in parallel with progress bar.

    Mutates each area dict in-place by adding a ``"web_research"`` key.
    """
    total = len(areas)
    if total == 0:
        return

    progress = ProgressTracker("LLM research", total)
    llm = LLMHelper(config.llm)
    agent = WebResearchAgent(llm)

    def _research_one(area: dict) -> None:
        result = agent.research_area(
            lat=area["center"]["lat"],
            lon=area["center"]["lon"],
            osm_tags=area.get("tags"),
        )
        area["web_research"] = result
        progress.advance()

    workers = max(1, config.pipeline.llm_workers)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_research_one, a) for a in areas]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                logger.exception("LLM research failed for an area")

    progress.finish()


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def find_areas(config_path: str) -> list[AreaResult]:
    """Find potential data-centre sites in German industrial areas.

    Optimised pipeline:
    1. Load configuration.
    2. Fetch Overpass data (parallel, chunked, cached) with progress.
    3. Apply proximity filters.
    4. Spatially sample to ``max_locations``.
    5. Run LLM web research on survivors only (parallel) with progress.
    6. Enrich and return.
    """
    sys.stderr.write("═══ find_areas pipeline ═══\n")

    # 1. Config
    config = load_config(config_path)

    # 2. Overpass (parallel + chunked + cached)
    client = OverpassClient()
    industrial, power_lines, water_sources, substations = _fetch_overpass_data(client, config)
    logger.info("Overpass totals: %d industrial, %s power lines, %s water, %s substations",
                len(industrial),
                len(power_lines) if power_lines else "–",
                len(water_sources) if water_sources else "–",
                len(substations) if substations else "–")

    # 3. Filter (fast, in-memory)
    engine = FilterEngine(config.filter)
    filtered = engine.apply_filters(industrial, power_lines, water_sources, substations)
    sys.stderr.write(f"  Filters: {len(industrial)} → {len(filtered)} areas\n")

    # 4. Spatial sampling
    max_loc = config.pipeline.max_locations
    sampled = _spatially_sample(filtered, max_loc)
    sys.stderr.write(f"  Sampled: {len(filtered)} → {len(sampled)} areas (max_locations={max_loc})\n")

    # 5. LLM research (only on sampled areas)
    _run_web_research(sampled, config)

    # 6. Enrich
    enricher = MetadataEnricher()
    results = enricher.enrich(sampled, power_lines, water_sources, config.filter)

    sys.stderr.write(f"  Done: {len(results)} results\n")
    sys.stderr.write("═══════════════════════════\n")
    return results
