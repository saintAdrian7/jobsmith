import httpx

from pipeline.config import Config
from pipeline.models import Lead
from pipeline.sources import SourceUnavailable, register


def _is_remote(location: str) -> bool:
    return "remote" in location.lower()


@register
class AtsSource:
    """Fetch postings from Greenhouse/Lever public board APIs for configured company slugs."""

    name = "ats"

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=20)

    def fetch(self, criteria: dict) -> list[Lead]:
        """Return leads for every configured slug; a slug missing on both boards is skipped."""
        companies = self.config.data.get("sources", {}).get("ats", {}).get("companies", [])
        if not companies:
            raise SourceUnavailable("no companies configured under sources.ats.companies")
        leads: list[Lead] = []
        for slug in companies:
            gh_leads = self._greenhouse(slug)
            if gh_leads is not None:
                leads.extend(gh_leads)
            else:
                leads.extend(self._lever(slug))
        return leads

    def _greenhouse(self, slug: str) -> list[Lead] | None:
        """Return leads if board exists, or None if board not found; never falls back when board exists with no jobs."""
        response = self.client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
        if response.status_code != 200:
            return None
        leads = []
        for job in response.json().get("jobs", []):
            loc = job.get("location", {}).get("name", "")
            leads.append(
                Lead(
                    company=slug,
                    title=job["title"],
                    url=job["absolute_url"],
                    source=self.name,
                    description=job.get("content", ""),
                    location=loc,
                    remote=_is_remote(loc) if loc else None,
                )
            )
        return leads

    def _lever(self, slug: str) -> list[Lead]:
        response = self.client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if response.status_code != 200:
            return []
        leads = []
        for job in response.json():
            loc = job.get("categories", {}).get("location", "")
            leads.append(
                Lead(
                    company=slug,
                    title=job["text"],
                    url=job["hostedUrl"],
                    source=self.name,
                    description=job.get("descriptionPlain", ""),
                    location=loc,
                    remote=_is_remote(loc) if loc else None,
                )
            )
        return leads


if __name__ == "__main__":
    from pathlib import Path

    leads = AtsSource(Config.load(Path.cwd())).fetch({})
    for lead in leads:
        print(lead.id, lead.company, "-", lead.title)
