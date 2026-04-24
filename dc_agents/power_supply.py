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
        f"power_cost: €{annual_cost:,.2f}/year "
        f"(load={ai_load_mw}MW, PUE={pue}, price={electricity_price_per_kwh:.4f}€/kWh)"
    )


power_supply_agent = Agent(
    name="Power Supply Agent",
    model="gpt-5.4-nano",
    instructions=(
        "Estimate annual electricity cost for a data center. Be very brief.\n"
        "Assume favorable industrial electricity rates and a modern efficient PUE (1.1-1.3 range).\n"
        "1. Web search industrial electricity price (EUR/kWh) near the coordinates.\n"
        "2. Estimate PUE for a modern AI DC at that location.\n"
        "3. Call compute_power_cost with your values.\n"
        "Final answer MUST include: power_cost: €<amount>/year"
    ),
    tools=[
        WebSearchTool(),
        compute_power_cost,
    ],
)
