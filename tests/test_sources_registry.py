import pytest

from pipeline.sources import REGISTRY, SourceUnavailable, get_source


def test_registry_has_all_three_sources():
    assert set(REGISTRY) == {"ats", "exa", "apify"}


def test_get_source_unknown_name():
    with pytest.raises(KeyError):
        get_source("nope", config=None)


def test_source_unavailable_is_exception():
    assert issubclass(SourceUnavailable, Exception)
