"""Web-Research-Agent – uses LLM-driven web search to gather industrial area info."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote_plus

import requests

from find_areas.llm_helper import LLMHelper
from find_areas.models import WebResearchResult

logger = logging.getLogger("find_areas")


class WebResearchAgent:
    """Uses the LLM Helper to orchestrate web searches for industrial area information.

    The agent instructs the LLM to search for an industrial area's name,
    available plots for sale, and their sizes.  It delegates actual HTTP
    searches to a simple requests-based backend (DuckDuckGo HTML or a
    configurable search API).
    """

    def __init__(self, llm: LLMHelper, search_api_key: str | None = None) -> None:
        """Initialise the agent.

        Args:
            llm: LLM helper instance for chat completions.
            search_api_key: Optional API key for a search provider.
                            When *None*, a simple DuckDuckGo HTML scrape is used.
        """
        self.llm = llm
        self.search_api_key = search_api_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def research_area(
        self,
        lat: float,
        lon: float,
        osm_tags: dict[str, str] | None = None,
    ) -> WebResearchResult:
        """Research an industrial area via LLM-driven web search.

        Args:
            lat: Latitude of the industrial area centre.
            lon: Longitude of the industrial area centre.
            osm_tags: Optional OSM tags (may already contain a name).

        Returns:
            A ``WebResearchResult`` with the gathered information.
            On any error a default result is returned (graceful degradation).
        """
        logger.info(
            "Researching industrial area at lat=%.4f, lon=%.4f (tags=%s)",
            lat, lon, osm_tags,
        )

        try:
            system_prompt = self._build_system_prompt()
            user_content = self._build_user_message(lat, lon, osm_tags)

            messages: list[dict[str, str]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            tools = [self._create_search_tool_definition()]

            final_response = self.llm.chat_with_tools(
                messages=messages,
                tools=tools,
                tool_executor=self._execute_tool_call,
            )

            logger.debug("LLM final response: %s", final_response)

            return self._parse_result(final_response)

        except Exception:
            logger.exception(
                "Error during web research for area at lat=%.4f, lon=%.4f",
                lat, lon,
            )
            return WebResearchResult()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Create the system prompt that instructs the LLM agent."""
        return (
            "Du bist ein Recherche-Assistent, der Informationen über "
            "Industriegebiete in Deutschland sammelt.\n\n"
            "Deine Aufgabe:\n"
            "1. Nutze das Tool 'web_search', um nach dem Industriegebiet zu suchen.\n"
            "2. Finde heraus: den Namen des Industriegebiets, ob Grundstücke zum "
            "Verkauf stehen, und deren Größen in Quadratmetern.\n"
            "3. Wenn du genug Informationen hast, antworte mit einem JSON-Objekt "
            "im folgenden Format (ohne Markdown-Code-Block):\n"
            "{\n"
            '  "area_name": "Name des Industriegebiets oder null",\n'
            '  "has_plots_for_sale": true/false,\n'
            '  "plot_sizes_sqm": [1000.0, 2000.0],\n'
            '  "confidence": 0.0-1.0,\n'
            '  "sources": ["https://example.com"]\n'
            "}\n\n"
            "Regeln:\n"
            "- confidence ist ein Wert zwischen 0.0 und 1.0, der angibt, "
            "wie sicher du dir bei den Ergebnissen bist.\n"
            "- Wenn du keine Informationen findest, setze confidence auf 0.0 "
            "und has_plots_for_sale auf false.\n"
            "- Antworte ausschließlich mit dem JSON-Objekt, ohne zusätzlichen Text."
        )

    @staticmethod
    def _build_user_message(
        lat: float,
        lon: float,
        osm_tags: dict[str, str] | None,
    ) -> str:
        """Build the initial user message with area context."""
        parts = [
            f"Recherchiere das Industriegebiet bei den Koordinaten "
            f"lat={lat}, lon={lon}."
        ]
        if osm_tags:
            name = osm_tags.get("name")
            if name:
                parts.append(f"Der OSM-Name ist: {name}.")
            tag_str = ", ".join(f"{k}={v}" for k, v in osm_tags.items())
            parts.append(f"Vorhandene OSM-Tags: {tag_str}.")
        return " ".join(parts)

    @staticmethod
    def _create_search_tool_definition() -> dict:
        """Create the OpenAI function-calling tool definition for web search."""
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Führt eine Websuche durch und gibt die Ergebnisse "
                    "als Text zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Der Suchbegriff für die Websuche.",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def _execute_tool_call(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call dispatched by the LLM.

        Currently only ``web_search`` is supported.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments (e.g. ``{"query": "..."}``).

        Returns:
            The tool result as a string.
        """
        if tool_name == "web_search":
            query = arguments.get("query", "")
            return self._perform_web_search(query)
        return f"Unknown tool: {tool_name}"

    def _perform_web_search(self, query: str) -> str:
        """Run a web search and return results as text.

        If a *search_api_key* was provided, it is passed as a query
        parameter to a configurable search endpoint.  Otherwise a simple
        DuckDuckGo HTML GET is used.

        Args:
            query: The search query string.

        Returns:
            Search result text (or an error message on failure).
        """
        logger.info("Searching for: %s", query)

        try:
            if self.search_api_key:
                return self._search_with_api(query)
            return self._search_duckduckgo(query)
        except Exception:
            logger.exception("Web search failed for query: %s", query)
            return "Fehler bei der Websuche. Keine Ergebnisse verfügbar."

    def _search_with_api(self, query: str) -> str:
        """Search using a configurable API key (e.g. SerpAPI)."""
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": self.search_api_key,
            "hl": "de",
            "gl": "de",
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        snippets: list[str] = []
        for result in data.get("organic_results", [])[:5]:
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            link = result.get("link", "")
            snippets.append(f"{title}\n{snippet}\n{link}")
        return "\n\n".join(snippets) if snippets else "Keine Ergebnisse gefunden."

    @staticmethod
    def _search_duckduckgo(query: str) -> str:
        """Fallback: simple DuckDuckGo HTML search."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; FindAreasBot/1.0; "
                "+https://github.com/find-areas)"
            ),
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        # Very lightweight HTML extraction – pull text from result snippets.
        # We intentionally avoid heavy parsing dependencies.
        text = resp.text
        snippets: list[str] = []
        marker = "result__snippet"
        idx = 0
        for _ in range(5):
            pos = text.find(marker, idx)
            if pos == -1:
                break
            # Find the next '>' after the class attribute
            start = text.find(">", pos)
            if start == -1:
                break
            end = text.find("<", start)
            if end == -1:
                break
            snippet = text[start + 1 : end].strip()
            if snippet:
                snippets.append(snippet)
            idx = end

        return "\n\n".join(snippets) if snippets else "Keine Ergebnisse gefunden."

    def _parse_result(self, llm_response: str) -> WebResearchResult:
        """Parse the LLM's JSON response into a ``WebResearchResult``.

        If parsing fails, a default (empty) result is returned.
        """
        try:
            # Strip potential markdown code fences
            cleaned = llm_response.strip()
            if cleaned.startswith("```"):
                # Remove opening fence (possibly ```json)
                first_newline = cleaned.index("\n")
                cleaned = cleaned[first_newline + 1 :]
            if cleaned.endswith("```"):
                cleaned = cleaned[: -3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            confidence = float(data.get("confidence", 0.0))
            # Clamp confidence to [0.0, 1.0]
            confidence = max(0.0, min(1.0, confidence))

            plot_sizes = data.get("plot_sizes_sqm", [])
            if not isinstance(plot_sizes, list):
                plot_sizes = []
            plot_sizes = [float(s) for s in plot_sizes]

            sources = data.get("sources", [])
            if not isinstance(sources, list):
                sources = []
            sources = [str(s) for s in sources]

            result = WebResearchResult(
                area_name=data.get("area_name"),
                has_plots_for_sale=bool(data.get("has_plots_for_sale", False)),
                plot_sizes_sqm=plot_sizes,
                confidence=confidence,
                sources=sources,
            )

            logger.debug("Parsed WebResearchResult: %s", result)
            return result

        except Exception:
            logger.exception("Failed to parse LLM response into WebResearchResult")
            return WebResearchResult()
