import httpx

from pipeline.llm import BaseProvider


class OpenAICompatProvider(BaseProvider):
    """Any OpenAI-compatible chat/completions endpoint (Mistral, OpenAI, Groq, Ollama)."""

    def _request(self, messages: list[dict]) -> httpx.Response:
        return self.client.post(
            f"{self.settings.get('base_url', '').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.settings.get("model", ""),
                "max_tokens": self.settings.get("max_tokens", 4096),
                "messages": messages,
            },
        )

    def _extract(self, body: dict) -> str:
        return body["choices"][0]["message"]["content"]
