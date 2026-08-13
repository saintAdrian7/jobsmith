import json
import time

import httpx

from pipeline.config import Config


class LLMError(Exception):
    """Raised on provider failures or unparseable model output."""


class BaseProvider:
    """Shared request/retry/JSON plumbing; subclasses define _request and _extract."""

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.settings = config.data.get("llm", {})
        self.api_key = config.env(self.settings.get("api_key_env", "ANTHROPIC_API_KEY"))
        self.client = client or httpx.Client(timeout=120)

    def complete(self, messages: list[dict], json_mode: bool = False) -> str | dict:
        """Run one completion; with json_mode, parse the reply as JSON or raise LLMError."""
        response = self._request(messages)
        if response.status_code in (429,) or response.status_code >= 500:
            time.sleep(2)
            response = self._request(messages)
        if response.status_code != 200:
            raise LLMError(f"{self.__class__.__name__}: HTTP {response.status_code}: {response.text[:200]}")
        text = self._extract(response.json())
        return _parse_json(text) if json_mode else text

    def _request(self, messages: list[dict]) -> httpx.Response:
        raise NotImplementedError

    def _extract(self, body: dict) -> str:
        raise NotImplementedError


def _parse_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"model returned invalid JSON: {e}") from e


def get_provider(config: Config, client: httpx.Client | None = None) -> BaseProvider:
    """Instantiate the provider named in config llm.provider."""
    from pipeline.llm.anthropic import AnthropicProvider
    from pipeline.llm.openai_compat import OpenAICompatProvider

    providers = {"anthropic": AnthropicProvider, "openai_compat": OpenAICompatProvider}
    name = config.data.get("llm", {}).get("provider", "anthropic")
    if name not in providers:
        raise LLMError(f"unknown provider '{name}'; choose from {sorted(providers)}")
    return providers[name](config, client=client)
