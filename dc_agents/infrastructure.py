"""Infrastructure Agent — estimates building, network, and cooling infrastructure costs."""

from agents import Agent, WebSearchTool, function_tool
from utils import estimate_ai_load


@function_tool
def compute_infrastructure_cost(
    latitude: float,
    longitude: float,
    total_area: float,
    building_cost_per_sqm: float,
    network_cost_per_mw: float,
    cooling_infra_cost_per_mw: float,
) -> str:
    """Compute total infrastructure cost (building + network + cooling hardware).

    Args:
        latitude: Site latitude.
        longitude: Site longitude.
        total_area: Total facility area in square metres.
        building_cost_per_sqm: Construction cost per m² in EUR.
        network_cost_per_mw: Network infrastructure cost per MW of IT load in EUR.
        cooling_infra_cost_per_mw: Cooling infrastructure capital cost per MW of IT load in EUR.
    """
    ai_load_mw = estimate_ai_load(total_area)

    building_cost = total_area * building_cost_per_sqm
    network_cost = ai_load_mw * network_cost_per_mw
    cooling_infra_cost = ai_load_mw * cooling_infra_cost_per_mw
    total_cost = building_cost + network_cost + cooling_infra_cost

    return (
        f"Infrastructure cost estimate:\n"
        f"  Location: ({latitude}, {longitude})\n"
        f"  Total area: {total_area:,.0f} m²\n"
        f"  Estimated AI load: {ai_load_mw} MW\n"
        f"  Building construction: €{building_cost:,.2f}\n"
        f"  Network infrastructure: €{network_cost:,.2f}\n"
        f"  Cooling infrastructure: €{cooling_infra_cost:,.2f}\n"
        f"  infrastructure_cost: €{total_cost:,.2f}"
    )


infrastructure_agent = Agent(
    name="Infrastructure Agent",
    model="gpt-5.4-mini",
    instructions=(
        "You are a specialist in data center construction and infrastructure costing.\n\n"
        "Given coordinates (latitude, longitude) and total area in m², you must:\n"
        "1. Use web search to research current construction costs for data center buildings "
        "in the region of the given coordinates (cost per m²).\n"
        "2. Research network infrastructure costs (fiber connectivity, redundant links) "
        "typically expressed per MW of IT load.\n"
        "3. Research cooling infrastructure capital costs (chillers, CRAH units, piping) "
        "per MW of IT load.\n"
        "4. Call compute_infrastructure_cost with your researched values.\n\n"
        "Your final answer MUST include the line:\n"
        "  infrastructure_cost: €<amount>\n"
        "where <amount> is the total estimated infrastructure capital cost in euros."
    ),
    tools=[
        WebSearchTool(),
        compute_infrastructure_cost,
    ],
)
