"""Orchestrator agent that coordinates the four cost estimation agents."""

from agents import Agent, function_tool

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
    model="gpt-5.4-mini",
    instructions=(
        "You are a data center site evaluation orchestrator.\n\n"
        "Given coordinates (latitude, longitude) and total area in m², you MUST:\n"
        "1. Call get_datacenter_capacity with the total area to obtain the facility power capacity.\n"
        "2. Call ALL FOUR cost estimation tools:\n"
        "   - estimate_land_cost — total land purchase cost\n"
        "   - estimate_infrastructure_cost — building, network, and cooling infrastructure capital cost\n"
        "   - estimate_power_cost — annual electricity cost\n"
        "   - estimate_cooling_cost — annual operational cooling cost\n\n"
        "Then compile a final summary report with all costs clearly listed in EUR.\n\n"
        "You MUST respond with ONLY a valid JSON object (no markdown, no extra text) "
        "in this exact format:\n"
        "{\n"
        '  "latitude": <float>,\n'
        '  "longitude": <float>,\n'
        '  "total_area_sqm": <float>,\n'
        '  "capacity_mw": <float>,\n'
        '  "capacity_w": <float>,\n'
        '  "land_cost_eur": <float>,\n'
        '  "infrastructure_cost_eur": <float>,\n'
        '  "power_cost_annual_eur": <float>,\n'
        '  "cooling_cost_annual_eur": <float>,\n'
        '  "total_capital_eur": <float>,\n'
        '  "total_annual_opex_eur": <float>\n'
        "}"
    ),
    tools=[
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
