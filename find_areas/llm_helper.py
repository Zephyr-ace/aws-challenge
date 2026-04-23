"""LLM Helper – generic wrapper around the OpenAI Chat Completions API."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

import openai

from find_areas.exceptions import LLMError
from find_areas.models import LLMConfig

logger = logging.getLogger("find_areas")

# Retry settings
_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 1.0
_BACKOFF_FACTOR = 2.0


class LLMHelper:
    """Generic wrapper around the OpenAI Chat Completions API.

    Supports plain chat completions as well as an iterative tool-use loop.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialise the helper with an OpenAI-compatible endpoint.

        Args:
            config: LLM connection parameters (base_url, api_key, model).
        """
        self.client = openai.OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        self.model = config.model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> dict:
        """Send a chat completion request to the OpenAI API.

        Args:
            messages: Conversation messages (role, content).
            tools: Optional tool definitions for function calling.
            temperature: Sampling temperature (default 0.0).

        Returns:
            The full API response as a dictionary.

        Raises:
            LLMError: On non-transient API errors or after retries exhausted.
        """
        logger.info("LLM request: model=%s, messages=%d, tools=%s",
                     self.model, len(messages),
                     len(tools) if tools else 0)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        return self._call_with_retry(**kwargs)

    def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        tool_executor: Callable,
        max_iterations: int = 5,
    ) -> str:
        """Run an iterative tool-use loop.

        1. Send messages to the LLM.
        2. If the LLM returns tool calls, execute them via *tool_executor*.
        3. Append tool results and send back to the LLM.
        4. Repeat until the LLM produces a final text response or
           *max_iterations* is reached.

        Args:
            messages: Initial conversation messages.
            tools: Tool definitions (OpenAI function-calling format).
            tool_executor: Callable that executes a tool call.
                           Signature: ``tool_executor(tool_name, arguments) -> str``
            max_iterations: Maximum number of tool-call cycles.

        Returns:
            The final text response from the LLM.
        """
        conversation = list(messages)  # shallow copy

        for iteration in range(max_iterations):
            response = self.chat(conversation, tools=tools)
            choice = response.choices[0]
            message = choice.message

            # If no tool calls, we have the final answer
            if not message.tool_calls:
                return message.content or ""

            # Append the assistant message (with tool calls) to conversation
            conversation.append(message)

            # Execute each tool call and collect results
            for tool_call in message.tool_calls:
                fn = tool_call.function
                tool_name = fn.name
                try:
                    arguments = json.loads(fn.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                logger.debug("Tool call [iter %d]: %s(%s)",
                             iteration + 1, tool_name, arguments)

                result = tool_executor(tool_name, arguments)

                logger.debug("Tool result [iter %d]: %s → %s",
                             iteration + 1, tool_name,
                             result[:200] if isinstance(result, str) else result)

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })

        # max_iterations exhausted – make one final call without tools
        # so the LLM can summarise what it has so far.
        response = self.chat(conversation, tools=None)
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_with_retry(self, **kwargs: Any) -> Any:
        """Call the OpenAI API with exponential-backoff retry for transient errors."""
        backoff = _INITIAL_BACKOFF_S

        for attempt in range(_MAX_RETRIES + 1):
            try:
                return self.client.chat.completions.create(**kwargs)
            except openai.RateLimitError as exc:
                if attempt < _MAX_RETRIES:
                    logger.warning("Rate limit hit, retrying in %.1fs (attempt %d/%d)",
                                   backoff, attempt + 1, _MAX_RETRIES)
                    time.sleep(backoff)
                    backoff *= _BACKOFF_FACTOR
                else:
                    raise LLMError(f"Rate limit exceeded after {_MAX_RETRIES} retries: {exc}") from exc
            except openai.AuthenticationError as exc:
                raise LLMError(f"Invalid API key: {exc}") from exc
            except openai.APIError as exc:
                if attempt < _MAX_RETRIES:
                    logger.warning("API error, retrying in %.1fs (attempt %d/%d): %s",
                                   backoff, attempt + 1, _MAX_RETRIES, exc)
                    time.sleep(backoff)
                    backoff *= _BACKOFF_FACTOR
                else:
                    raise LLMError(f"API error after {_MAX_RETRIES} retries: {exc}") from exc

        # Should not be reached, but just in case
        raise LLMError("Unexpected retry loop exit")  # pragma: no cover
