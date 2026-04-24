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
        f"Land cost estimate:\n"
        f"  Location: ({latitude}, {longitude})\n"
        f"  Total area: {total_area:,.0f} m²\n"
        f"  Estimated AI load: {ai_load_mw} MW\n"
        f"  Price per m²: €{price_per_sqm:,.2f}\n"
        f"  land_cost: €{total_cost:,.2f}"
    )


land_cost_agent = Agent(
    name="Land Cost Agent",
    model="gpt-5.4-mini",
    instructions=(
        "You are a specialist in commercial and industrial land valuation for data center sites.\n\n"
        "Given a set of coordinates (latitude, longitude) and a total area in m², you must:\n"
        "1. Use web search to research current land prices near the given coordinates. "
        "Focus on industrial/commercial land suitable for data centers.\n"
        "2. Determine a realistic price per m² in EUR for that location.\n"
        "3. Call the compute_land_cost tool with the coordinates, area, and your estimated price per m².\n\n"
        "Your final answer MUST include the line:\n"
        "  land_cost: €<amount>\n"
        "where <amount> is the total estimated purchase cost in euros."
    ),
    tools=[
        WebSearchTool(),
        compute_land_cost,
    ],
)
