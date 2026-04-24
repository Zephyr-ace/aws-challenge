"""End-to-end pipeline: fetch candidate areas, estimate costs, write cache."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

from agents import Runner

from area_fetching import find_areas
from orchestrator import orchestrator_agent
from utils import estimate_ai_load

logger = logging.getLogger("pipeline")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

CACHE_FILE = Path("site_cache.json")
AREA_CACHE_FILE = Path("area_cache.json")


def _fallback_areas() -> list[dict]:
    """Return a handful of real German industrial areas as fallback when Overpass is down."""
    return [
        {"latitude": 52.4497, "longitude": 13.5072, "area_sqm": 120000, "industrial_area_name": "Adlershof Berlin", "has_plots_for_sale": True, "plot_sizes_sqm": [15000.0], "research_confidence": 0.0, "research_sources": []},
        {"latitude": 51.3127, "longitude": 12.3731, "area_sqm": 85000, "industrial_area_name": "Industriepark Leipzig Nord", "has_plots_for_sale": True, "plot_sizes_sqm": [20000.0], "research_confidence": 0.0, "research_sources": []},
        {"latitude": 50.1109, "longitude": 8.6821, "area_sqm": 60000, "industrial_area_name": "Fechenheim Frankfurt", "has_plots_for_sale": False, "plot_sizes_sqm": [], "research_confidence": 0.0, "research_sources": []},
        {"latitude": 48.7758, "longitude": 9.1829, "area_sqm": 95000, "industrial_area_name": "Sindelfingen Stuttgart", "has_plots_for_sale": True, "plot_sizes_sqm": [10000.0], "research_confidence": 0.0, "research_sources": []},
        {"latitude": 51.4556, "longitude": 7.0116, "area_sqm": 110000, "industrial_area_name": "Essen-Kray Ruhrgebiet", "has_plots_for_sale": True, "plot_sizes_sqm": [25000.0], "research_confidence": 0.0, "research_sources": []},
        {"latitude": 53.5511, "longitude": 9.9937, "area_sqm": 75000, "industrial_area_name": "Billbrook Hamburg", "has_plots_for_sale": False, "plot_sizes_sqm": [], "research_confidence": 0.0, "research_sources": []},
        {"latitude": 48.1351, "longitude": 11.5820, "area_sqm": 50000, "industrial_area_name": "Moosach München", "has_plots_for_sale": True, "plot_sizes_sqm": [8000.0], "research_confidence": 0.0, "research_sources": []},
    ]


def _parse_cost_json(raw: str) -> dict:
    """Extract a JSON object from the orchestrator's output."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```json\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned)
    return json.loads(cleaned.strip())


async def estimate_site(lat: float, lon: float, area_sqm: float) -> dict:
    """Run the cost orchestrator for a single candidate site."""
    prompt = (
        f"Estimate all costs for building and operating an AI data center at "
        f"coordinates ({lat}, {lon}) with a total area of {area_sqm:,.0f} m²."
    )
    result = await Runner.run(orchestrator_agent, input=prompt)
    try:
        data = _parse_cost_json(result.final_output)
    except (json.JSONDecodeError, TypeError):
        # Fallback: store raw output and compute what we can locally
        mw = estimate_ai_load(area_sqm)
        data = {
            "latitude": lat,
            "longitude": lon,
            "total_area_sqm": area_sqm,
            "capacity_mw": mw,
            "capacity_w": mw * 1_000_000,
            "raw_output": result.final_output,
        }
    return data


async def run_pipeline(config_path: str, max_sites: int | None = None, refresh_areas: bool = False) -> list[dict]:
    """Fetch areas, estimate costs for each, write cache file.

    Args:
        config_path: Path to the area_fetching YAML config.
        max_sites: Maximum number of candidate sites to estimate costs for.
                   If None, all sites are processed.
        refresh_areas: If True, ignore area cache and re-fetch from Overpass.
    """

    # 1. Fetch candidate areas (use area cache if available)
    if AREA_CACHE_FILE.exists() and not refresh_areas:
        logger.info("Loading areas from cache: %s", AREA_CACHE_FILE)
        areas = json.loads(AREA_CACHE_FILE.read_text(encoding="utf-8"))
    else:
        logger.info("Fetching candidate areas from config: %s", config_path)
        try:
            areas = find_areas(config_path)
            if not areas:
                logger.warning("Area fetching returned 0 results, using fallback sample areas")
                areas = _fallback_areas()
        except Exception as e:
            logger.warning("Area fetching failed (%s), using fallback sample areas", e)
            areas = _fallback_areas()

        # Cache the fetched areas for next time
        AREA_CACHE_FILE.write_text(json.dumps(areas, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Area cache written to %s (%d areas)", AREA_CACHE_FILE, len(areas))
    logger.info("Found %d candidate areas", len(areas))

    if not areas:
        logger.warning("No candidate areas found. Nothing to estimate.")
        return []

    # Apply max_sites limit
    if max_sites is not None and max_sites < len(areas):
        logger.info("Limiting to %d of %d areas", max_sites, len(areas))
        areas = areas[:max_sites]

    # 2. Estimate costs for each area sequentially
    results: list[dict] = []
    for i, area in enumerate(areas, 1):
        lat = area["latitude"]
        lon = area["longitude"]
        area_sqm = area["area_sqm"]
        name = area.get("industrial_area_name") or "Unknown"

        logger.info(
            "[%d/%d] Estimating costs for %s (%.4f, %.4f) — %.0f m²",
            i, len(areas), name, lat, lon, area_sqm,
        )

        site_data = await estimate_site(lat, lon, area_sqm)

        # Merge area_fetching metadata into the result
        site_data["industrial_area_name"] = name
        site_data["has_plots_for_sale"] = area.get("has_plots_for_sale", False)
        site_data["plot_sizes_sqm"] = area.get("plot_sizes_sqm", [])
        site_data["research_confidence"] = area.get("research_confidence", 0.0)
        if "distance_power_line_km" in area:
            site_data["distance_power_line_km"] = area["distance_power_line_km"]
        if "distance_water_source_km" in area:
            site_data["distance_water_source_km"] = area["distance_water_source_km"]

        results.append(site_data)

    # 3. Write cache file
    CACHE_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Cache written to %s (%d sites)", CACHE_FILE, len(results))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch data center candidate areas and estimate costs."
    )
    parser.add_argument(
        "--config",
        default="area_config.yaml",
        help="Path to area_fetching YAML config (default: area_config.yaml)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        dest="max_sites",
        help="Maximum number of candidate sites to estimate costs for (default: all)",
    )
    parser.add_argument(
        "--refresh-areas",
        action="store_true",
        default=False,
        help="Ignore area cache and re-fetch from Overpass API",
    )
    args = parser.parse_args()
    results = asyncio.run(run_pipeline(args.config, args.max_sites, args.refresh_areas))

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Processed {len(results)} candidate sites")
    print(f"  Results cached to: {CACHE_FILE}")
    print(f"{'='*60}\n")
    for r in results:
        name = r.get("industrial_area_name", "?")
        cap = r.get("capacity_w", "?")
        cap_str = f"{cap:,.0f} W" if isinstance(cap, (int, float)) else cap
        total_cap = r.get("total_capital_eur", "?")
        total_opex = r.get("total_annual_opex_eur", "?")
        cap_eur = f"€{total_cap:,.0f}" if isinstance(total_cap, (int, float)) else total_cap
        opex_eur = f"€{total_opex:,.0f}/yr" if isinstance(total_opex, (int, float)) else total_opex
        print(f"  {name}: {cap_str} | CapEx {cap_eur} | OpEx {opex_eur}")


if __name__ == "__main__":
    main()
