"""Config-Loader: reads, validates, and returns AppConfig from a YAML file."""

from __future__ import annotations

import logging
import os
import re

import yaml

from find_areas.exceptions import ConfigError
from find_areas.models import AppConfig, FilterConfig, LLMConfig

logger = logging.getLogger("find_areas")

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ``${VAR}`` placeholders with the corresponding environment variable."""

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        try:
            return os.environ[var_name]
        except KeyError:
            raise ConfigError(
                f"Environment variable '{var_name}' is not set"
            ) from None

    return _ENV_VAR_PATTERN.sub(_replacer, value)


def _resolve_env_vars_recursive(obj: object) -> object:
    """Walk a nested dict/list structure and resolve env-var placeholders in strings."""
    if isinstance(obj, str):
        return _resolve_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars_recursive(item) for item in obj]
    return obj


def load_config(config_path: str) -> AppConfig:
    """Load and validate an application configuration from a YAML file.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.

    Returns
    -------
    AppConfig
        Fully validated configuration object with defaults applied.

    Raises
    ------
    ConfigError
        If the file cannot be read, parsed, or contains invalid values.
    """

    # --- read & parse --------------------------------------------------------
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        raise ConfigError(f"Configuration file not found: {config_path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML configuration: {exc}") from None

    if not isinstance(raw, dict):
        raise ConfigError("Configuration file must contain a YAML mapping at the top level")

    # --- resolve environment variables ---------------------------------------
    raw = _resolve_env_vars_recursive(raw)

    # --- build LLMConfig -----------------------------------------------------
    llm_raw = raw.get("llm", {}) or {}
    llm_config = LLMConfig(
        base_url=llm_raw.get("base_url", LLMConfig.base_url),
        api_key=llm_raw.get("api_key", LLMConfig.api_key),
        model=llm_raw.get("model", LLMConfig.model),
    )

    # --- build FilterConfig --------------------------------------------------
    filter_raw = raw.get("filter", {}) or {}
    power_line_raw = filter_raw.get("proximity_power_line", {}) or {}
    water_source_raw = filter_raw.get("proximity_water_source", {}) or {}

    filter_config = FilterConfig(
        proximity_power_line_enabled=power_line_raw.get(
            "enabled", FilterConfig.proximity_power_line_enabled
        ),
        proximity_water_source_enabled=water_source_raw.get(
            "enabled", FilterConfig.proximity_water_source_enabled
        ),
        max_distance_power_line_km=power_line_raw.get(
            "max_distance_km", FilterConfig.max_distance_power_line_km
        ),
        max_distance_water_source_km=water_source_raw.get(
            "max_distance_km", FilterConfig.max_distance_water_source_km
        ),
    )

    # --- validation ----------------------------------------------------------
    _validate_llm(llm_config)
    _validate_filter(filter_config)

    config = AppConfig(filter=filter_config, llm=llm_config)

    # --- logging -------------------------------------------------------------
    logger.info("Configuration loaded from %s", config_path)
    logger.info(
        "Filter settings – power_line: enabled=%s (max %.1f km), "
        "water_source: enabled=%s (max %.1f km)",
        config.filter.proximity_power_line_enabled,
        config.filter.max_distance_power_line_km,
        config.filter.proximity_water_source_enabled,
        config.filter.max_distance_water_source_km,
    )
    logger.info("LLM settings – base_url=%s, model=%s", config.llm.base_url, config.llm.model)

    return config


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_llm(cfg: LLMConfig) -> None:
    if not cfg.base_url.startswith(("http://", "https://")):
        raise ConfigError(
            f"llm.base_url must start with http:// or https://, got: {cfg.base_url!r}"
        )
    if not cfg.model or not cfg.model.strip():
        raise ConfigError("llm.model must not be empty")


def _validate_filter(cfg: FilterConfig) -> None:
    if cfg.max_distance_power_line_km <= 0:
        raise ConfigError(
            f"max_distance_power_line_km must be > 0, got {cfg.max_distance_power_line_km}"
        )
    if cfg.max_distance_water_source_km <= 0:
        raise ConfigError(
            f"max_distance_water_source_km must be > 0, got {cfg.max_distance_water_source_km}"
        )
