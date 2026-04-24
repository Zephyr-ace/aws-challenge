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
        f"infrastructure_cost: €{total_cost:,.2f} "
        f"(building=€{building_cost:,.2f}, network=€{network_cost:,.2f}, cooling_infra=€{cooling_infra_cost:,.2f})"
    )


infrastructure_agent = Agent(
    name="Infrastructure Agent",
    model="gpt-5.4-nano",
    instructions=(
        "Estimate data center infrastructure costs. Be very brief.\n"
        "Assume modern efficient construction with economies of scale. Use competitive but realistic rates.\n"
        "1. Web search construction cost/m², network cost/MW, cooling infra cost/MW for the region.\n"
        "2. Call compute_infrastructure_cost with your values.\n"
        "Final answer MUST include: infrastructure_cost: €<amount>"
    ),
    tools=[
        WebSearchTool(),
        compute_infrastructure_cost,
    ],
)
