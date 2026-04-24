"""Power Supply Agent — estimates ongoing electricity costs at a given location."""

from agents import Agent, WebSearchTool, function_tool
from utils import estimate_ai_load


@function_tool
def compute_power_cost(
    latitude: float,
    longitude: float,
    total_area: float,
    electricity_price_per_kwh: float,
    pue: float,
) -> str:
    """Compute annual electricity cost for operating the data center.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.
        total_area: Total facility area in square metres.
        electricity_price_per_kwh: Local electricity price in EUR per kWh.
        pue: Power Usage Effectiveness ratio (typically 1.1–1.6).
    """
    ai_load_mw = estimate_ai_load(total_area)
    total_power_mw = ai_load_mw * pue
    annual_kwh = total_power_mw * 1000.0 * 8760.0  # MW -> kW * hours/year
    annual_cost = annual_kwh * electricity_price_per_kwh

    return (
        f"Power supply cost estimate:\n"
        f"  Location: ({latitude}, {longitude})\n"
        f"  Total area: {total_area:,.0f} m²\n"
        f"  Estimated AI load: {ai_load_mw} MW\n"
        f"  PUE: {pue}\n"
        f"  Total facility power: {total_power_mw:.2f} MW\n"
        f"  Electricity price: €{electricity_price_per_kwh:.4f}/kWh\n"
        f"  Annual consumption: {annual_kwh:,.0f} kWh\n"
        f"  power_cost: €{annual_cost:,.2f}/year"
    )


power_supply_agent = Agent(
    name="Power Supply Agent",
    model="gpt-5.4-mini",
    instructions=(
        "You are a specialist in energy markets and data center power procurement.\n\n"
        "Given coordinates (latitude, longitude) and total area in m², you must:\n"
        "1. Use web search to find the current industrial electricity price (EUR/kWh) "
        "in the region of the given coordinates.\n"
        "2. Estimate a realistic PUE (Power Usage Effectiveness) for a modern AI data center "
        "at that location, considering the local climate.\n"
        "3. Call compute_power_cost with the coordinates, area, electricity price, and PUE.\n\n"
        "Your final answer MUST include the line:\n"
        "  power_cost: €<amount>/year\n"
        "where <amount> is the estimated annual electricity cost in euros."
    ),
    tools=[
        WebSearchTool(),
        compute_power_cost,
    ],
)
