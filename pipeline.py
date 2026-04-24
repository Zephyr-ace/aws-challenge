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
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Keep our pipeline logger at INFO, silence noisy libraries
logging.getLogger("pipeline").setLevel(logging.INFO)
logging.getLogger("find_areas").setLevel(logging.WARNING)
# Silence OpenAI / httpx / agents SDK chatter
for _quiet in ("openai", "httpx", "httpcore", "agents", "openai._base_client"):
    logging.getLogger(_quiet).setLevel(logging.WARNING)

TOTAL_CACHE_FILE = Path("total_site_cache.json")
AREA_CACHE_FILE = Path("area_cache.json")
BATCH_CACHE_DIR_10 = Path("mini_caches_10")
BATCH_CACHE_DIR_100 = Path("mini_caches_100")
BATCH_SIZE_SMALL = 10
BATCH_SIZE_LARGE = 100
MAX_CONCURRENT = 5


def _fallback_areas() -> list[dict]:
    """Return a handful of real German industrial areas as fallback when Overpass is down."""
    return [
        {"latitude": 52.4497, "longitude": 13.5072, "area_sqm": 120000, "industrial_area_name": "Adlershof Berlin"},
        {"latitude": 51.3127, "longitude": 12.3731, "area_sqm": 85000, "industrial_area_name": "Industriepark Leipzig Nord"},
        {"latitude": 50.1109, "longitude": 8.6821, "area_sqm": 60000, "industrial_area_name": "Fechenheim Frankfurt"},
        {"latitude": 48.7758, "longitude": 9.1829, "area_sqm": 95000, "industrial_area_name": "Sindelfingen Stuttgart"},
        {"latitude": 51.4556, "longitude": 7.0116, "area_sqm": 110000, "industrial_area_name": "Essen-Kray Ruhrgebiet"},
        {"latitude": 53.5511, "longitude": 9.9937, "area_sqm": 75000, "industrial_area_name": "Billbrook Hamburg"},
        {"latitude": 48.1351, "longitude": 11.5820, "area_sqm": 50000, "industrial_area_name": "Moosach München"},
    ]


def _parse_cost_json(raw: str) -> dict:
    """Extract a JSON object from the orchestrator's output."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```json\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned)
    return json.loads(cleaned.strip())


async def estimate_site(lat: float, lon: float, area_sqm: float, area: dict | None = None) -> dict:
    """Run the cost orchestrator for a single candidate site."""
    parts = [f"Evaluate data center site at ({lat}, {lon})."]

    if area_sqm > 0:
        parts.append(f"Total area: {area_sqm:,.0f} m².")
    else:
        parts.append(
            "Area unknown — research the industrial zone and estimate a realistic "
            "buildable plot size (not the entire zone, just what a single DC campus could use)."
        )

    # Pass substation metadata if available
    if area:
        sub_name = area.get("nearest_substation_name")
        sub_voltage = area.get("nearest_substation_voltage")
        sub_dist = area.get("distance_substation_km")
        sub_operator = area.get("nearest_substation_operator")
        if sub_name and sub_dist is not None:
            parts.append(
                f"Nearest substation: {sub_name} ({sub_operator or '?'}, "
                f"{sub_voltage or '?'}V) at {sub_dist:.1f} km."
            )
        ind_name = area.get("industrial_area_name")
        if ind_name:
            parts.append(f"Industrial area: {ind_name}.")

    prompt = " ".join(parts)
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


async def run_pipeline(
    config_path: str,
    max_sites: int | None = None,
    refresh_areas: bool = False,
    fetch_only: bool = False,
) -> list[dict]:
    """Fetch areas, estimate costs for each, write cache file.

    Args:
        config_path: Path to the area_fetching YAML config.
        max_sites: Maximum number of candidate sites to estimate costs for.
                   If None, all sites are processed.
        refresh_areas: If True, ignore area cache and re-fetch from Overpass.
        fetch_only: If True, stop after fetching and caching areas.
    """

    # 1. Fetch candidate areas (use area cache if available)
    if AREA_CACHE_FILE.exists() and not refresh_areas and not fetch_only:
        logger.debug("Loading areas from cache: %s", AREA_CACHE_FILE)
        areas = json.loads(AREA_CACHE_FILE.read_text(encoding="utf-8"))
    else:
        logger.debug("Fetching candidate areas from config: %s", config_path)
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
        logger.debug("Area cache written to %s (%d areas)", AREA_CACHE_FILE, len(areas))
    logger.debug("Found %d candidate areas", len(areas))

    if fetch_only:
        logger.debug("--fetch-only: stopping after area cache.")
        return areas

    if not areas:
        logger.warning("No candidate areas found. Nothing to estimate.")
        return []

    # Apply max_sites limit
    if max_sites is not None and max_sites < len(areas):
        logger.debug("Limiting to %d of %d areas", max_sites, len(areas))
        areas = areas[:max_sites]

    # 2. Always estimate fresh — skip resume from mini_caches
    completed_results: list[dict] = []
    skip_count = 0

    # Estimate costs in parallel, writing batch caches
    BATCH_CACHE_DIR_10.mkdir(exist_ok=True)
    BATCH_CACHE_DIR_100.mkdir(exist_ok=True)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(areas)

    async def _estimate_one(idx: int, area: dict) -> dict:
        async with semaphore:
            lat = area["latitude"]
            lon = area["longitude"]
            area_sqm = area["area_sqm"]
            name = area.get("industrial_area_name") or "Unknown"

            logger.debug(
                "[%d/%d] Estimating costs for %s (%.4f, %.4f) — %.0f m²",
                idx + 1, total, name, lat, lon, area_sqm,
            )

            site_data = await estimate_site(lat, lon, area_sqm, area)

            # Merge area_fetching metadata
            site_data["industrial_area_name"] = name
            if "distance_power_line_km" in area:
                site_data["distance_power_line_km"] = area["distance_power_line_km"]
            if "distance_water_source_km" in area:
                site_data["distance_water_source_km"] = area["distance_water_source_km"]

            return site_data

    # Launch all tasks concurrently (semaphore limits parallelism)
    tasks = [_estimate_one(i, a) for i, a in enumerate(areas)]
    results: list[dict] = []
    batch_num_10 = skip_count // BATCH_SIZE_SMALL
    batch_num_100 = skip_count // BATCH_SIZE_LARGE

    for coro in asyncio.as_completed(tasks):
        site_data = await coro
        results.append(site_data)
        # Live one-line summary per site
        _name = site_data.get("industrial_area_name", "?")
        _cap = site_data.get("capacity_w")
        _capex = site_data.get("total_capital_eur")
        _opex = site_data.get("total_annual_opex_eur")
        _cap_s = f"{_cap:,.0f} W" if isinstance(_cap, (int, float)) else "?"
        _capex_s = f"€{_capex:,.0f}" if isinstance(_capex, (int, float)) else "?"
        _opex_s = f"€{_opex:,.0f}/yr" if isinstance(_opex, (int, float)) else "?"
        print(f"  [{len(results)}/{total}] {_name}: {_cap_s} | CapEx {_capex_s} | OpEx {_opex_s}")

        # Write batch cache every 10 completions
        if len(results) % BATCH_SIZE_SMALL == 0:
            batch_num_10 += 1
            batch_file = BATCH_CACHE_DIR_10 / f"site_cache_batch_{batch_num_10}.json"
            batch_data = results[-BATCH_SIZE_SMALL:]
            batch_file.write_text(json.dumps(batch_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug("Batch-10 #%d written to %s (%d sites)", batch_num_10, batch_file, len(batch_data))

        # Write batch cache every 100 completions
        if len(results) % BATCH_SIZE_LARGE == 0:
            batch_num_100 += 1
            batch_file = BATCH_CACHE_DIR_100 / f"site_cache_batch_{batch_num_100}.json"
            batch_data = results[-BATCH_SIZE_LARGE:]
            batch_file.write_text(json.dumps(batch_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug("Batch-100 #%d written to %s (%d sites)", batch_num_100, batch_file, len(batch_data))

    # Write final partial batches if there are leftovers
    if len(results) % BATCH_SIZE_SMALL != 0:
        batch_num_10 += 1
        batch_file = BATCH_CACHE_DIR_10 / f"site_cache_batch_{batch_num_10}.json"
        batch_data = results[-(len(results) % BATCH_SIZE_SMALL):]
        batch_file.write_text(json.dumps(batch_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Batch-10 #%d written to %s (%d sites)", batch_num_10, batch_file, len(batch_data))

    if len(results) % BATCH_SIZE_LARGE != 0:
        batch_num_100 += 1
        batch_file = BATCH_CACHE_DIR_100 / f"site_cache_batch_{batch_num_100}.json"
        batch_data = results[-(len(results) % BATCH_SIZE_LARGE):]
        batch_file.write_text(json.dumps(batch_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Batch-100 #%d written to %s (%d sites)", batch_num_100, batch_file, len(batch_data))

    # 3. Write total cache file (resumed + new)
    all_results = completed_results + results
    TOTAL_CACHE_FILE.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Total cache written to %s (%d sites)", TOTAL_CACHE_FILE, len(all_results))

    return all_results


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
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        default=False,
        help="Only fetch and cache areas, skip cost estimation",
    )
    args = parser.parse_args()
    results = asyncio.run(run_pipeline(args.config, args.max_sites, args.refresh_areas, args.fetch_only))

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Done — {len(results)} sites evaluated")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
