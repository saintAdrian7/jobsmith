import json

from pipeline.models import Lead
from pipeline.store import Store


def make_lead(**overrides) -> Lead:
    base = dict(company="Acme", title="Engineer", url="https://acme.dev/j/1", source="ats")
    base.update(overrides)
    return Lead(**base)


def test_save_lead_writes_file_and_index(tmp_path):
    store = Store(tmp_path)
    lead = make_lead()
    assert store.save_lead(lead) is True
    assert (tmp_path / "leads" / f"{lead.id}.json").exists()
    entry = store.read_index("leads")[lead.id]
    assert entry["company"] == "Acme"
    assert entry["status"] == "new"


def test_save_lead_dedups(tmp_path):
    store = Store(tmp_path)
    assert store.save_lead(make_lead()) is True
    assert store.save_lead(make_lead(title="Engineer II")) is False


def test_load_and_update_preserve_status(tmp_path):
    store = Store(tmp_path)
    lead = make_lead()
    store.save_lead(lead)
    store.set_lead_status(lead.id, "scored")
    loaded = store.load_lead(lead.id)
    loaded.score = 0.9
    store.update_lead(loaded)
    index = store.read_index("leads")
    assert index[lead.id]["score"] == 0.9
    assert index[lead.id]["status"] == "scored"


def test_write_index_is_atomic_no_tmp_left(tmp_path):
    store = Store(tmp_path)
    store.write_index("leads", {"a": 1})
    leftovers = list((tmp_path / "leads").glob("*.tmp"))
    assert leftovers == []
    assert json.loads((tmp_path / "leads" / "index.json").read_text())["a"] == 1


def test_artifacts_and_output_index(tmp_path):
    store = Store(tmp_path)
    path = store.save_artifact("abc123", "resume", "# Resume")
    assert path.read_text(encoding="utf-8") == "# Resume"
    store.record_output("abc123", "Acme", ["resume"])
    assert store.read_index("outputs")["abc123"]["artifacts"] == ["resume"]


def test_mark_application(tmp_path):
    store = Store(tmp_path)
    store.mark("abc123", "applied")
    assert store.read_applications()["abc123"] == "applied"
