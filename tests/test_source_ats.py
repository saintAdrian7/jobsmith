import httpx

from pipeline.config import Config
from pipeline.sources import SourceUnavailable, get_source

GREENHOUSE_BODY = {
    "jobs": [
        {
            "title": "Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": {"name": "Remote - Anywhere"},
            "content": "Build things.",
        }
    ]
}

LEVER_BODY = [
    {
        "text": "Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/beta/2",
        "categories": {"location": "Nairobi"},
        "descriptionPlain": "APIs.",
    }
]


def make_config(tmp_path, companies):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    config = Config.load(tmp_path)
    config.data = {"sources": {"ats": {"companies": companies}}}
    return config


def transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_greenhouse_normalization(tmp_path):
    def handler(request):
        if "greenhouse" in request.url.host:
            return httpx.Response(200, json=GREENHOUSE_BODY)
        return httpx.Response(404)

    source = get_source("ats", make_config(tmp_path, ["acme"]), client=transport(handler))
    leads = source.fetch({})
    assert len(leads) == 1
    assert leads[0].company == "acme"
    assert leads[0].title == "Software Engineer"
    assert leads[0].remote is True
    assert leads[0].source == "ats"


def test_falls_back_to_lever_and_detects_non_remote(tmp_path):
    def handler(request):
        if "greenhouse" in request.url.host:
            return httpx.Response(404)
        return httpx.Response(200, json=LEVER_BODY)

    leads = get_source("ats", make_config(tmp_path, ["beta"]), client=transport(handler)).fetch({})
    assert leads[0].title == "Backend Engineer"
    assert leads[0].remote is False


def test_slug_missing_on_both_boards_is_skipped(tmp_path):
    def handler(request):
        return httpx.Response(404)

    leads = get_source("ats", make_config(tmp_path, ["ghost"]), client=transport(handler)).fetch({})
    assert leads == []


def test_no_companies_raises_unavailable(tmp_path):
    source = get_source("ats", make_config(tmp_path, []))
    try:
        source.fetch({})
        assert False, "expected SourceUnavailable"
    except SourceUnavailable as e:
        assert "companies" in str(e)


def test_greenhouse_with_no_jobs_does_not_fall_back_to_lever(tmp_path):
    lever_called = []

    def handler(request):
        if "greenhouse" in request.url.host:
            return httpx.Response(200, json={"jobs": []})
        if "lever" in request.url.host:
            lever_called.append(True)
            raise AssertionError("Lever should not be queried when Greenhouse exists with no jobs")
        return httpx.Response(404)

    leads = get_source("ats", make_config(tmp_path, ["acme"]), client=transport(handler)).fetch({})
    assert leads == []
    assert not lever_called
