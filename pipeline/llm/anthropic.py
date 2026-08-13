import httpx

from pipeline.llm import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API over REST."""

    def _request(self, messages: list[dict]) -> httpx.Response:
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        payload = {
            "model": self.settings.get("model", "claude-sonnet-5"),
            "max_tokens": self.settings.get("max_tokens", 4096),
            "messages": [m for m in messages if m["role"] != "system"],
        }
        if system:
            payload["system"] = system
        return self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json=payload,
        )

    def _extract(self, body: dict) -> str:
        return "".join(block["text"] for block in body["content"] if block["type"] == "text")
