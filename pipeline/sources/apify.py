import os

import httpx

from pipeline.config import Config
from pipeline.models import Lead
from pipeline.sources import SourceUnavailable, register


@register
class ApifySource:
    """Run a configured Apify actor synchronously and map its dataset items to Leads."""

    name = "apify"

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=120)

    def fetch(self, criteria: dict) -> list[Lead]:
        """Invoke the actor and normalize items; items without a url are skipped."""
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            raise SourceUnavailable("APIFY_TOKEN not set; add it to .env or skip this source")
        settings = self.config.data.get("sources", {}).get("apify", {})
        if not settings.get("actor"):
            raise SourceUnavailable("no actor configured under sources.apify.actor")
        response = self.client.post(
            f"https://api.apify.com/v2/acts/{settings['actor']}/run-sync-get-dataset-items",
            params={"token": token},
            json=settings.get("input", {}),
        )
        response.raise_for_status()
        leads = []
        for item in response.json():
            url = item.get("url") or item.get("link")
            if not url:
                continue
            location = item.get("location", "")
            leads.append(
                Lead(
                    company=item.get("company") or item.get("companyName") or "unknown",
                    title=item.get("title", "Untitled posting"),
                    url=url,
                    source=self.name,
                    description=item.get("description", ""),
                    location=location,
                    remote="remote" in location.lower(),
                )
            )
        return leads


if __name__ == "__main__":
    from pathlib import Path

    for lead in ApifySource(Config.load(Path.cwd())).fetch({}):
        print(lead.id, lead.company, "-", lead.title)
