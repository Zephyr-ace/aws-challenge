"""Quick integration test for the substation query + filter pipeline."""

from __future__ import annotations

import sys
import time

from area_fetching.distance import haversine
from area_fetching.filter_engine import FilterEngine
from area_fetching.models import FilterConfig
from area_fetching.overpass import OverpassClient


def main() -> None:
    client = OverpassClient()

    # ── 1. Query substations ────────────────────────────────────────
    print("Querying transmission substations in Germany...")
    t0 = time.time()
    substations = client.query_substations()
    dt = time.time() - t0
    print(f"  → {len(substations)} substations fetched in {dt:.1f}s\n")

    if not substations:
        print("ERROR: No substations returned – aborting.")
        sys.exit(1)

    # Show a few examples
    print("Sample substations:")
    for sub in substations[:5]:
        center = sub.get("center") or sub
        tags = sub.get("tags", {})
        print(
            f"  {tags.get('name', '(unnamed)'):<40} "
            f"voltage={tags.get('voltage', '?'):<20} "
            f"operator={tags.get('operator', '?'):<20} "
            f"({center.get('lat', '?')}, {center.get('lon', '?')})"
        )
    print()

    # ── 2. Build synthetic industrial areas for testing ─────────────
    # Known German industrial zones with approximate centres
    test_areas = [
        {"name": "Industriepark Höchst (Frankfurt)", "lat": 50.0856, "lon": 8.5397},
        {"name": "Chempark Leverkusen", "lat": 51.0333, "lon": 6.9833},
        {"name": "Industriegebiet Bitterfeld-Wolfen", "lat": 51.6236, "lon": 12.3286},
        {"name": "Gewerbegebiet Falkenhagen (rural)", "lat": 52.8500, "lon": 12.0500},
        {"name": "Industriepark Schwarze Pumpe", "lat": 51.5350, "lon": 14.3530},
    ]

    fake_areas = []
    for ta in test_areas:
        fake_areas.append({
            "center": {"lat": ta["lat"], "lon": ta["lon"]},
            "tags": {"name": ta["name"], "landuse": "industrial"},
            "type": "way",
            "id": hash(ta["name"]),
        })

    # ── 3. Run filter with different thresholds ─────────────────────
    for threshold_km in [10.0, 20.0, 30.0, 50.0]:
        cfg = FilterConfig(
            proximity_substation_enabled=True,
            max_distance_substation_km=threshold_km,
        )
        engine = FilterEngine(cfg)
        filtered = engine.apply_filters(fake_areas, None, None, substations)

        print(f"Threshold {threshold_km:5.1f} km → {len(filtered)}/{len(fake_areas)} areas pass")
        for area in filtered:
            print(
                f"  ✓ {area['tags']['name']:<45} "
                f"dist={area['_distance_substation_km']:.2f} km  "
                f"substation={area.get('_substation_name', '?')}  "
                f"voltage={area.get('_substation_voltage', '?')}  "
                f"operator={area.get('_substation_operator', '?')}"
            )
        print()

    # ── 4. Sanity checks ───────────────────────────────────────────
    print("Running sanity checks...")

    # Every substation should have lat/lon resolvable
    resolved = 0
    for sub in substations:
        c = sub.get("center")
        if c and "lat" in c and "lon" in c:
            resolved += 1
        elif "lat" in sub and "lon" in sub:
            resolved += 1
    pct = resolved / len(substations) * 100
    print(f"  Coordinate resolution: {resolved}/{len(substations)} ({pct:.1f}%)")
    assert pct > 95, f"Too many substations without coordinates ({pct:.1f}%)"

    # At least some should have voltage tags
    with_voltage = sum(
        1 for s in substations if s.get("tags", {}).get("voltage")
    )
    pct_v = with_voltage / len(substations) * 100
    print(f"  With voltage tag:      {with_voltage}/{len(substations)} ({pct_v:.1f}%)")

    # At least some should have operator tags
    with_operator = sum(
        1 for s in substations if s.get("tags", {}).get("operator")
    )
    pct_o = with_operator / len(substations) * 100
    print(f"  With operator tag:     {with_operator}/{len(substations)} ({pct_o:.1f}%)")

    # Höchst (Frankfurt) should definitely be within 30 km of a substation
    cfg30 = FilterConfig(
        proximity_substation_enabled=True,
        max_distance_substation_km=30.0,
    )
    engine30 = FilterEngine(cfg30)
    result30 = engine30.apply_filters([fake_areas[0]], None, None, substations)
    assert len(result30) == 1, (
        "Industriepark Höchst should be within 30 km of a transmission substation"
    )
    print(f"  Höchst sanity check:   PASS (nearest substation {result30[0]['_distance_substation_km']:.2f} km)")

    print("\nAll checks passed ✓")


if __name__ == "__main__":
    main()
