import pytest

from pipeline.config import ConfigError
from pipeline.generate import generate_for, load_truth
from pipeline.models import Lead
from pipeline.store import Store


class FakeProvider:
    def __init__(self):
        self.calls = []

    def complete(self, messages, json_mode=False):
        self.calls.append(messages)
        return f"artifact {len(self.calls)}"


class FailingProvider:
    def __init__(self, fail_on_call=2):
        self.calls = []
        self.fail_on_call = fail_on_call

    def complete(self, messages, json_mode=False):
        self.calls.append(messages)
        if len(self.calls) == self.fail_on_call:
            raise Exception("Provider failed")
        return f"artifact {len(self.calls)}"


def make_truth(root):
    truth = root / "truth"
    (truth / "writing").mkdir(parents=True)
    (truth / "resume.md").write_text("# Adrian", encoding="utf-8")
    (truth / "facts.yaml").write_text("skills: [python]", encoding="utf-8")
    (truth / "writing" / "sample.md").write_text("my voice", encoding="utf-8")


def seed_lead(store):
    lead = Lead(company="Acme", title="Eng", url="https://a.co/1", source="ats")
    store.save_lead(lead)
    return lead


def test_load_truth_concatenates_with_headers(tmp_path):
    make_truth(tmp_path)
    truth = load_truth(tmp_path)
    assert "## resume.md" in truth and "# Adrian" in truth
    assert "## facts.yaml" in truth
    assert "## sample.md" in truth and "my voice" in truth


def test_load_truth_requires_resume(tmp_path):
    with pytest.raises(ConfigError, match="resume.md"):
        load_truth(tmp_path)


def test_generate_writes_artifacts_and_updates_state(tmp_path):
    make_truth(tmp_path)
    store = Store(tmp_path)
    lead = seed_lead(store)
    provider = FakeProvider()
    paths = generate_for(lead.id, store, provider, load_truth(tmp_path), ["resume", "cover_letter"])
    assert [p.name for p in paths] == ["resume.md", "cover_letter.md"]
    assert store.read_index("outputs")[lead.id]["artifacts"] == ["resume", "cover_letter"]
    assert store.read_index("leads")[lead.id]["status"] == "generated"
    assert store.read_applications()[lead.id] == "generated"
    prompt_text = str(provider.calls[0])
    assert "Acme" in prompt_text and "# Adrian" in prompt_text


def test_generate_refuses_overwrite_without_force(tmp_path):
    make_truth(tmp_path)
    store = Store(tmp_path)
    lead = seed_lead(store)
    generate_for(lead.id, store, FakeProvider(), load_truth(tmp_path), ["resume"])
    with pytest.raises(FileExistsError):
        generate_for(lead.id, store, FakeProvider(), load_truth(tmp_path), ["resume"])
    generate_for(lead.id, store, FakeProvider(), load_truth(tmp_path), ["resume"], force=True)


def test_generate_cleans_up_on_partial_failure(tmp_path):
    make_truth(tmp_path)
    store = Store(tmp_path)
    lead = seed_lead(store)
    provider = FailingProvider(fail_on_call=2)
    with pytest.raises(Exception, match="Provider failed"):
        generate_for(lead.id, store, provider, load_truth(tmp_path), ["resume", "cover_letter"])
    output_dir = store.root / "outputs" / lead.id
    assert not output_dir.exists(), "Output directory should be cleaned up after partial failure"
    assert store.read_index("leads")[lead.id]["status"] == "new", "Lead status should remain unchanged"
    assert lead.id not in store.read_applications(), "Lead should not be in applications tracker"


def test_generate_force_failure_restores_prior_artifacts(tmp_path):
    make_truth(tmp_path)
    store = Store(tmp_path)
    lead = seed_lead(store)
    generate_for(lead.id, store, FakeProvider(), load_truth(tmp_path), ["resume", "cover_letter"])
    output_dir = store.root / "outputs" / lead.id
    original_resume = (output_dir / "resume.md").read_text(encoding="utf-8")
    original_cover_letter = (output_dir / "cover_letter.md").read_text(encoding="utf-8")
    failing = FailingProvider(fail_on_call=2)
    with pytest.raises(Exception, match="Provider failed"):
        generate_for(lead.id, store, failing, load_truth(tmp_path), ["resume", "cover_letter"], force=True)
    assert output_dir.exists(), "original artifacts should remain intact after a failed force regenerate"
    assert (output_dir / "resume.md").read_text(encoding="utf-8") == original_resume
    assert (output_dir / "cover_letter.md").read_text(encoding="utf-8") == original_cover_letter
    assert not output_dir.with_name(output_dir.name + ".bak").exists(), "no .bak dir should be left behind"
