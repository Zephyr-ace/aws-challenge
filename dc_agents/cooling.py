"""Cooling Agent — estimates operational cooling costs for the data center."""

from agents import Agent, WebSearchTool, function_tool
from utils import estimate_ai_load


@function_tool
def compute_cooling_cost(
    latitude: float,
    longitude: float,
    total_area: float,
    cooling_cost_per_mw_year: float,
    free_cooling_fraction: float,
) -> str:
    """Compute annual operational cooling cost.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.
        total_area: Total facility area in square metres.
        cooling_cost_per_mw_year: Annual cooling operational cost per MW of IT load in EUR.
        free_cooling_fraction: Fraction of the year where free cooling is available (0.0–1.0).
    """
    ai_load_mw = estimate_ai_load(total_area)

    base_annual_cost = ai_load_mw * cooling_cost_per_mw_year
    # Free cooling reduces mechanical cooling costs proportionally
    effective_cost = base_annual_cost * (1.0 - free_cooling_fraction)

    return (
        f"cooling_cost: €{effective_cost:,.2f}/year "
        f"(load={ai_load_mw}MW, free_cooling={free_cooling_fraction:.0%})"
    )


cooling_agent = Agent(
    name="Cooling Agent",
    model="gpt-5.4-nano",
    instructions=(
        "Estimate annual cooling cost for a data center. Be very brief.\n"
        "Assume modern cooling tech with good free cooling utilization where climate allows.\n"
        "1. Web search local climate at the coordinates for free cooling potential.\n"
        "2. Estimate free cooling fraction and cooling cost/MW/year.\n"
        "3. Call compute_cooling_cost with your values.\n"
        "Final answer MUST include: cooling_cost: €<amount>/year"
    ),
    tools=[
        WebSearchTool(),
        compute_cooling_cost,
    ],
)
