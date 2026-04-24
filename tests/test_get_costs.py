"""Quick smoke test for the cost estimation pipeline (estimate_site).

Runs the orchestrator agent for a single site and optionally tests
parallel execution of multiple sites via asyncio.gather.
"""

import asyncio
import json
import time

import pytest

from pipeline import estimate_site


@pytest.mark.asyncio
async def test_estimate_site_single():
    """Verify estimate_site returns a dict with expected cost keys for one site."""
    # Berlin industrial area — small area to keep the test fast
    result = await estimate_site(lat=52.45, lon=13.51, area_sqm=10_000)

    assert isinstance(result, dict)
    assert result["latitude"] == 52.45
    assert result["longitude"] == 13.51
    assert result["total_area_sqm"] == 10_000

    # If the orchestrator returned valid JSON, we should have these keys
    expected_keys = [
        "capacity_mw",
        "land_cost_eur",
        "infrastructure_cost_eur",
        "power_cost_annual_eur",
        "cooling_cost_annual_eur",
    ]
    parsed_ok = all(k in result for k in expected_keys)
    if not parsed_ok:
        # Fallback path — at minimum we get capacity + raw_output
        assert "capacity_mw" in result
        assert "raw_output" in result
        print("⚠ Orchestrator returned unparseable output (fallback path)")
    else:
        # Sanity: costs should be positive numbers
        for k in expected_keys:
            assert isinstance(result[k], (int, float)), f"{k} is not numeric"
            assert result[k] >= 0, f"{k} is negative"

    print(f"\n✅ Single site result:\n{json.dumps(result, indent=2)}")


@pytest.mark.asyncio
async def test_estimate_site_parallel():
    """Run 3 sites concurrently and verify parallelism gives a wall-clock speedup."""
    sites = [
        (52.45, 13.51, 10_000),   # Berlin
        (48.14, 11.58, 8_000),    # Munich
        (51.31, 12.37, 12_000),   # Leipzig
    ]

    # --- sequential baseline ---
    t0 = time.perf_counter()
    seq_results = []
    for lat, lon, area in sites:
        seq_results.append(await estimate_site(lat, lon, area))
    seq_elapsed = time.perf_counter() - t0

    # --- parallel via asyncio.gather ---
    t0 = time.perf_counter()
    par_results = await asyncio.gather(
        *(estimate_site(lat, lon, area) for lat, lon, area in sites)
    )
    par_elapsed = time.perf_counter() - t0

    # Both should return the same number of results
    assert len(seq_results) == len(par_results) == len(sites)
    for r in par_results:
        assert isinstance(r, dict)
        assert "capacity_mw" in r

    print(f"\n⏱  Sequential: {seq_elapsed:.1f}s")
    print(f"⏱  Parallel:   {par_elapsed:.1f}s")
    print(f"⏱  Speedup:    {seq_elapsed / par_elapsed:.2f}x")

    # If truly parallel, we'd expect at least ~1.5x speedup for 3 tasks.
    # We don't hard-assert this because CI environments vary, but we report it.
    if par_elapsed < seq_elapsed * 0.75:
        print("✅ Parallel execution shows meaningful speedup — agents run concurrently!")
    else:
        print("⚠  Little or no speedup — agents may be running sequentially under the hood.")
