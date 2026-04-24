"""Orchestrator agent that coordinates the four cost estimation agents."""

from agents import Agent, WebSearchTool, function_tool

from dc_agents.land_cost import land_cost_agent
from dc_agents.infrastructure import infrastructure_agent
from dc_agents.power_supply import power_supply_agent
from dc_agents.cooling import cooling_agent
from utils import estimate_ai_load


@function_tool
def get_datacenter_capacity(total_area: float) -> str:
    """Return the estimated AI compute capacity for a given facility area.

    Args:
        total_area: Total facility area in square metres.
    """
    mw = estimate_ai_load(total_area)
    watts = mw * 1_000_000
    return f"Estimated AI load: {mw} MW ({watts:,.0f} W)"


orchestrator_agent = Agent(
    name="Data Center Cost Orchestrator",
    model="gpt-5.4-nano",
    instructions=(
        "You evaluate data center sites. Be extremely brief in all responses.\n"
        "Assume modern, efficient designs and competitive market conditions.\n\n"
        "Given coordinates, optionally area in m², and substation info:\n"
        "0. If area is unknown/zero, estimate a realistic BUILDABLE PLOT size (typically "
        "10,000-50,000 m² for a single DC campus, not the entire industrial zone).\n"
        "1. Call get_datacenter_capacity with the area.\n"
        "2. Web search the industrial area name and plot availability.\n"
        "3. Call ALL FOUR cost tools: estimate_land_cost, estimate_infrastructure_cost, "
        "estimate_power_cost, estimate_cooling_cost.\n\n"
        "IMPORTANT cost factors to consider:\n"
        "- Grid connection cost: use substation distance provided. Estimate ~€1M/km for "
        "HV line + transformer costs. Add this to infrastructure_cost.\n"
        "- Closer substations with higher voltage = cheaper and more reliable power.\n"
        "- Factor in redundancy (N+1 power/cooling) in infrastructure costs.\n"
        "- Consider local renewable energy availability for power pricing.\n\n"
        "Respond with ONLY this JSON (no markdown):\n"
        "{\n"
        '  "latitude": <float>, "longitude": <float>,\n'
        '  "total_area_sqm": <float>, "capacity_mw": <float>, "capacity_w": <float>,\n'
        '  "industrial_area_name": "<str or null>",\n'
        '  "has_plots_for_sale": <bool>, "plot_sizes_sqm": [<float>],\n'
        '  "land_cost_eur": <float>, "infrastructure_cost_eur": <float>,\n'
        '  "grid_connection_cost_eur": <float>,\n'
        '  "power_cost_annual_eur": <float>, "cooling_cost_annual_eur": <float>,\n'
        '  "total_capital_eur": <float>, "total_annual_opex_eur": <float>\n'
        "}"
    ),
    tools=[
        WebSearchTool(),
        get_datacenter_capacity,
        land_cost_agent.as_tool(
            tool_name="estimate_land_cost",
            tool_description="Estimate the total land purchase cost for a data center site given coordinates and area.",
        ),
        infrastructure_agent.as_tool(
            tool_name="estimate_infrastructure_cost",
            tool_description="Estimate building, network, and cooling infrastructure capital costs for a data center site.",
        ),
        power_supply_agent.as_tool(
            tool_name="estimate_power_cost",
            tool_description="Estimate annual electricity costs for operating a data center at the given location.",
        ),
        cooling_agent.as_tool(
            tool_name="estimate_cooling_cost",
            tool_description="Estimate annual operational cooling costs for a data center at the given location.",
        ),
    ],
)
