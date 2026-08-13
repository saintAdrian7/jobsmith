import httpx
import pytest

from pipeline.config import Config
from pipeline.sources import SourceUnavailable, get_source

APIFY_ITEMS = [
    {"title": "Junior Dev", "companyName": "Beta", "link": "https://b.co/j/9", "location": "Remote"},
    {"title": "No URL item", "companyName": "Ghost"},
]


def make_config(tmp_path, actor="user~actor"):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    config = Config.load(tmp_path)
    config.data = {"sources": {"apify": {"actor": actor, "input": {"rows": 10}}}}
    return config


def test_fetch_maps_items_and_skips_missing_url(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")

    def handler(request):
        assert "user~actor" in str(request.url)
        assert request.url.params["token"] == "t"
        return httpx.Response(201, json=APIFY_ITEMS)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    leads = get_source("apify", make_config(tmp_path), client=client).fetch({})
    assert len(leads) == 1
    assert leads[0].company == "Beta"
    assert leads[0].remote is True
    assert leads[0].source == "apify"


def test_fetch_missing_location_is_unknown_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")
    items = [{"title": "T", "companyName": "Beta", "link": "https://b.co/j/9"}]

    def handler(request):
        return httpx.Response(201, json=items)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    leads = get_source("apify", make_config(tmp_path), client=client).fetch({})
    assert leads[0].remote is None


def test_missing_token_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(SourceUnavailable, match="APIFY_TOKEN"):
        get_source("apify", make_config(tmp_path)).fetch({})


def test_missing_actor_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")
    with pytest.raises(SourceUnavailable, match="actor"):
        get_source("apify", make_config(tmp_path, actor="")).fetch({})
