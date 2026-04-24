"""Shared utility functions for data center cost estimation."""


def estimate_ai_load(total_area: float) -> float:
    """Estimate the AI compute load (in MW) based on total facility area in m².

    Assumes a high-density AI data center layout:
    - ~65% of gross area is usable whitespace (modern efficient layout)
    - Power density of ~20 kW per rack
    - ~1 rack per 5 m² of usable whitespace

    Args:
        total_area: Total facility footprint in square metres.

    Returns:
        Estimated AI compute load in megawatts (MW).
    """
    usable_ratio = 0.65
    kw_per_rack = 20.0
    sqm_per_rack = 5.0

    usable_area = total_area * usable_ratio
    num_racks = usable_area / sqm_per_rack
    total_kw = num_racks * kw_per_rack
    total_mw = total_kw / 1000.0
    return round(total_mw, 2)
