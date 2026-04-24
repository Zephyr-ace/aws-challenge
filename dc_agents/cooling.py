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
        f"Cooling cost estimate:\n"
        f"  Location: ({latitude}, {longitude})\n"
        f"  Total area: {total_area:,.0f} m²\n"
        f"  Estimated AI load: {ai_load_mw} MW\n"
        f"  Base cooling cost: €{base_annual_cost:,.2f}/year\n"
        f"  Free cooling fraction: {free_cooling_fraction:.0%}\n"
        f"  cooling_cost: €{effective_cost:,.2f}/year"
    )


cooling_agent = Agent(
    name="Cooling Agent",
    model="gpt-5.4-mini",
    instructions=(
        "You are a specialist in data center thermal management and cooling economics.\n\n"
        "Given coordinates (latitude, longitude) and total area in m², you must:\n"
        "1. Use web search to research the local climate at the given coordinates "
        "(average temperatures, humidity) to determine free cooling potential.\n"
        "2. Estimate the fraction of the year where free/economizer cooling can be used.\n"
        "3. Research typical annual mechanical cooling operational costs per MW of IT load.\n"
        "4. Call compute_cooling_cost with your researched values.\n\n"
        "Your final answer MUST include the line:\n"
        "  cooling_cost: €<amount>/year\n"
        "where <amount> is the estimated annual operational cooling cost in euros."
    ),
    tools=[
        WebSearchTool(),
        compute_cooling_cost,
    ],
)
