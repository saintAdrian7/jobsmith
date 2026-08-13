import httpx
import pytest

from pipeline.config import Config
from pipeline.sources import SourceUnavailable, get_source

EXA_BODY = {
    "results": [
        {
            "title": "Founding Engineer at Acme",
            "url": "https://www.acme.dev/careers/founding-engineer",
            "text": "We are hiring remotely.",
        }
    ]
}


def make_config(tmp_path, query="startup jobs"):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    config = Config.load(tmp_path)
    config.data = {"sources": {"exa": {"query": query, "num_results": 5}}}
    return config


def test_fetch_normalizes_results(tmp_path, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")

    def handler(request):
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(200, json=EXA_BODY)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    leads = get_source("exa", make_config(tmp_path), client=client).fetch({})
    assert leads[0].company == "acme"
    assert leads[0].title == "Founding Engineer at Acme"
    assert leads[0].source == "exa"


def test_missing_key_raises_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(SourceUnavailable, match="EXA_API_KEY"):
        get_source("exa", make_config(tmp_path)).fetch({})


def test_missing_query_raises_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")
    with pytest.raises(SourceUnavailable, match="query"):
        get_source("exa", make_config(tmp_path, query="")).fetch({})
