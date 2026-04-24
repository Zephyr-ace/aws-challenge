"""Data models for the find_areas pipeline."""

from dataclasses import dataclass, field
from typing import NotRequired, TypedDict


@dataclass
class LLMConfig:
    """Configuration for the LLM (OpenAI-compatible API)."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class FilterConfig:
    """Configuration for proximity filter criteria."""

    proximity_power_line_enabled: bool = False
    proximity_water_source_enabled: bool = False
    proximity_substation_enabled: bool = False
    max_distance_power_line_km: float = 20.0
    max_distance_water_source_km: float = 1.0
    max_distance_substation_km: float = 30.0


@dataclass
class AppConfig:
    """Top-level application configuration."""

    filter: FilterConfig = field(default_factory=FilterConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


@dataclass
class WebResearchResult:
    """Result of a web research query for an industrial area."""

    area_name: str | None = None
    has_plots_for_sale: bool = False
    plot_sizes_sqm: list[float] = field(default_factory=list)
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)


class AreaResult(TypedDict):
    """Pipeline output for a single potential data center site."""

    # Required fields
    latitude: float
    longitude: float
    area_sqm: float
    industrial_area_name: str | None
    has_plots_for_sale: bool
    plot_sizes_sqm: list[float]
    research_confidence: float
    research_sources: list[str]
    # Optional fields (only present when corresponding criteria are active)
    distance_power_line_km: NotRequired[float]
    water_source_name: NotRequired[str]
    distance_water_source_km: NotRequired[float]
    nearest_substation_name: NotRequired[str | None]
    nearest_substation_voltage: NotRequired[str | None]
    nearest_substation_operator: NotRequired[str | None]
    distance_substation_km: NotRequired[float]
