import httpx

from pipeline.config import Config


class SourceUnavailable(Exception):
    """Raised when a source cannot run (missing key or configuration)."""


REGISTRY: dict[str, type] = {}


def register(cls: type) -> type:
    """Class decorator: add a source class to REGISTRY under its name."""
    REGISTRY[cls.name] = cls
    return cls


def get_source(name: str, config: Config, client: httpx.Client | None = None):
    """Instantiate a registered source by name."""
    return REGISTRY[name](config, client=client)


from pipeline.sources import ats, exa, apify  # noqa: E402,F401  (self-registration)
