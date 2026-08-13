from pipeline.sources import SourceUnavailable, register


@register
class Stub:
    name = "apify"

    def __init__(self, config, client=None):
        self.config = config

    def fetch(self, criteria: dict) -> list:
        raise SourceUnavailable("not implemented")
