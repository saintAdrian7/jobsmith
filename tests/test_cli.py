import pytest

import pipeline.cli as cli
from pipeline.models import Lead
from pipeline.store import Store


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "sources:\n  ats:\n    companies: []\n", encoding="utf-8"
    )
    (tmp_path / "iep.yaml").write_text("must:\n  remote_required: false\n", encoding="utf-8")
    truth = tmp_path / "truth" / "writing"
    truth.mkdir(parents=True)
    (tmp_path / "truth" / "resume.md").write_text("# Me", encoding="utf-8")
    return tmp_path


class FakeSource:
    name = "fake"

    def __init__(self, leads):
        self.leads = leads

    def fetch(self, criteria):
        return self.leads


def seed(root, n=2, status=None):
    store = Store(root)
    leads = [Lead(company=f"C{i}", title="Eng", url=f"https://c{i}.co/1", source="ats") for i in range(n)]
    for lead in leads:
        store.save_lead(lead)
        if status:
            store.set_lead_status(lead.id, status)
    return store, leads


def test_source_command_reports_skip_when_unconfigured(root, capsys):
    assert cli.main(["source", "--source", "ats"], root=root) == 0
    out = capsys.readouterr().out
    assert "ats: skipped" in out


def test_source_command_saves_and_dedups(root, monkeypatch, capsys):
    lead = Lead(company="Acme", title="Eng", url="https://a.co/1", source="fake")
    monkeypatch.setitem(cli_registry(), "fake", lambda config, client=None: FakeSource([lead, lead]))
    assert cli.main(["source", "--source", "fake"], root=root) == 0
    out = capsys.readouterr().out
    assert "fake: sourced 1" in out and "duplicate 1" in out


def cli_registry():
    from pipeline.sources import REGISTRY

    return REGISTRY


def test_score_command(root, monkeypatch, capsys):
    seed(root)
    monkeypatch.setattr(
        cli, "get_provider", lambda config: type("P", (), {"complete": lambda self, m, json_mode=False: {"score": 0.5, "rationale": "ok"}})()
    )
    assert cli.main(["score"], root=root) == 0
    assert "0.5" in capsys.readouterr().out


def test_generate_top_picks_best_scored(root, monkeypatch, capsys):
    store, leads = seed(root, n=2, status="scored")
    for i, lead in enumerate(leads):
        loaded = store.load_lead(lead.id)
        loaded.score = 0.2 + i * 0.6
        store.update_lead(loaded)
    monkeypatch.setattr(
        cli, "get_provider", lambda config: type("P", (), {"complete": lambda self, m, json_mode=False: "content"})()
    )
    assert cli.main(["generate", "--top", "1"], root=root) == 0
    outputs = store.read_index("outputs")
    assert len(outputs) == 1
    assert list(outputs.values())[0]["company"] == "C1"


def test_status_and_mark(root, capsys):
    _, leads = seed(root)
    assert cli.main(["mark", leads[0].id, "applied"], root=root) == 0
    assert cli.main(["status"], root=root) == 0
    out = capsys.readouterr().out
    assert "leads" in out and "applied" in out


def test_config_error_returns_1(tmp_path, capsys):
    assert cli.main(["status"], root=tmp_path) == 1
    assert "config.yaml" in capsys.readouterr().out


def test_generate_without_force_on_existing_outputs_returns_1(root, monkeypatch, capsys):
    store, leads = seed(root, n=1, status="scored")
    lead = leads[0]
    loaded = store.load_lead(lead.id)
    loaded.score = 0.8
    store.update_lead(loaded)
    monkeypatch.setattr(
        cli, "get_provider", lambda config: type("P", (), {"complete": lambda self, m, json_mode=False: "content"})()
    )
    # Generate successfully the first time
    assert cli.main(["generate", lead.id], root=root) == 0
    capsys.readouterr()
    # Try to generate again without --force; should fail with return code 1
    assert cli.main(["generate", lead.id], root=root) == 1
    out = capsys.readouterr().out
    assert "--force" in out
