"""CLI entry point for the data center cost estimation system."""

import argparse
import asyncio

from agents import Runner

from orchestrator import orchestrator_agent


async def run(lat: float, lon: float, area: float) -> None:
    prompt = (
        f"Estimate all costs for building and operating an AI data center at "
        f"coordinates ({lat}, {lon}) with a total area of {area:,.0f} m²."
    )
    result = await Runner.run(orchestrator_agent, input=prompt)
    print(result.final_output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate data center site costs using multi-agent system."
    )
    parser.add_argument("--lat", type=float, required=True, help="Site latitude")
    parser.add_argument("--lon", type=float, required=True, help="Site longitude")
    parser.add_argument("--area", type=float, required=True, help="Total area in m²")
    args = parser.parse_args()

    asyncio.run(run(args.lat, args.lon, args.area))


if __name__ == "__main__":
    main()
