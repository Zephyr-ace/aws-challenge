"""Custom exceptions for the find_areas pipeline."""


class ConfigError(Exception):
    """Raised when the configuration file is missing or contains invalid values."""


class OverpassTimeoutError(Exception):
    """Raised when the Overpass API does not respond within the timeout."""


class LLMError(Exception):
    """Raised when the LLM API returns an error (rate limit, invalid key, etc.)."""
