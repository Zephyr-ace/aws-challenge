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
