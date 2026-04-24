"""Main pipeline for the find_areas application."""

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
from area_fetching.models import AreaResult
from area_fetching.overpass import OverpassClient
from area_fetching.progress import ProgressTracker
from area_fetching.web_research_agent import WebResearchAgent

logger = logging.getLogger("find_areas")


# ------------------------------------------------------------------
# Spatial sampling – pick *n* areas spread evenly across Germany
# ------------------------------------------------------------------

def _spatially_sample(areas: list[dict], n: int) -> list[dict]:
    """Select up to *n* areas that are spatially well-distributed.

    Uses a greedy farthest-point sampling strategy on an
    Equirectangular projection so that the selected subset covers
    Germany as evenly as possible.
    """
    if len(areas) <= n:
        return list(areas)

    # Build projected coordinate array (km-scale)
    coords = np.empty((len(areas), 2), dtype=np.float64)
    for i, a in enumerate(areas):
        lat = a["center"]["lat"]
        lon = a["center"]["lon"]
        coords[i, 0] = radians(lat) * 6371.0
        coords[i, 1] = radians(lon) * cos(radians(lat)) * 6371.0

    selected_idx: list[int] = []
    # Seed with the area closest to the centroid of all points
    centroid = coords.mean(axis=0)
    dists_to_centroid = np.sum((coords - centroid) ** 2, axis=1)
    first = int(np.argmin(dists_to_centroid))
    selected_idx.append(first)

    # min_dist[i] = distance from point i to the nearest selected point
    min_dist = np.sum((coords - coords[first]) ** 2, axis=1)

    for _ in range(n - 1):
        # Pick the point farthest from any already-selected point
        next_idx = int(np.argmax(min_dist))
        selected_idx.append(next_idx)
        # Update min distances
        new_dists = np.sum((coords - coords[next_idx]) ** 2, axis=1)
        min_dist = np.minimum(min_dist, new_dists)

    logger.info(
        "Spatial sampling: selected %d of %d areas",
        len(selected_idx), len(areas),
    )
    return [areas[i] for i in selected_idx]
