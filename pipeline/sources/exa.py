import os
from urllib.parse import urlparse

import httpx

from pipeline.config import Config
from pipeline.models import Lead
from pipeline.sources import SourceUnavailable, register


def _company_from_url(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    return host.split(".")[0]


@register
class ExaSource:
    """Discover postings via Exa semantic web search."""

    name = "exa"

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=30)

    def fetch(self, criteria: dict) -> list[Lead]:
        """Search Exa with the configured query and normalize results to Leads."""
        if not os.environ.get("EXA_API_KEY"):
            raise SourceUnavailable("EXA_API_KEY not set; add it to .env or skip this source")
        settings = self.config.data.get("sources", {}).get("exa", {})
        if not settings.get("query"):
            raise SourceUnavailable("no query configured under sources.exa.query")
        response = self.client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": os.environ["EXA_API_KEY"]},
            json={
                "query": settings["query"],
                "numResults": settings.get("num_results", 25),
                "contents": {"text": True},
            },
        )
        response.raise_for_status()
        return [
            Lead(
                company=_company_from_url(item["url"]),
                title=item.get("title", "") or "Untitled posting",
                url=item["url"],
                source=self.name,
                description=item.get("text", ""),
            )
            for item in response.json().get("results", [])
        ]


if __name__ == "__main__":
    from pathlib import Path

    for lead in ExaSource(Config.load(Path.cwd())).fetch({}):
        print(lead.id, lead.company, "-", lead.title)
