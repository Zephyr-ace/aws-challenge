"""Land Cost Agent — estimates purchase cost of land based on location and size."""

from agents import Agent, WebSearchTool, function_tool
from utils import estimate_ai_load


@function_tool
def compute_land_cost(
    latitude: float,
    longitude: float,
    total_area: float,
    price_per_sqm: float,
) -> str:
    """Compute total land purchase cost.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.
        total_area: Total land area in square metres.
        price_per_sqm: Estimated price per square metre in EUR.
    """
    ai_load_mw = estimate_ai_load(total_area)
    total_cost = total_area * price_per_sqm
    return (
        f"land_cost: €{total_cost:,.2f} "
        f"(area={total_area:,.0f}m², price={price_per_sqm:,.2f}€/m², load={ai_load_mw}MW)"
    )


land_cost_agent = Agent(
    name="Land Cost Agent",
    model="gpt-5.4-nano",
    instructions=(
        "Estimate land cost for a data center site. Be very brief.\n"
        "Favor competitive industrial land pricing — these are industrial zones, not prime city center.\n"
        "1. Web search industrial land prices near the coordinates.\n"
        "2. Call compute_land_cost with your estimated price/m².\n"
        "Final answer MUST include: land_cost: €<amount>"
    ),
    tools=[
        WebSearchTool(),
        compute_land_cost,
    ],
)
