from pipeline.llm import LLMError
from pipeline.models import Lead
from pipeline.score import score_leads
from pipeline.store import Store


class FakeProvider:
    def __init__(self, results):
        self.results = list(results)

    def complete(self, messages, json_mode=False):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def seed(store, n):
    leads = [Lead(company=f"C{i}", title="Eng", url=f"https://c{i}.co/1", source="ats") for i in range(n)]
    for lead in leads:
        store.save_lead(lead)
    return leads


def test_scores_new_leads_and_sorts(tmp_path):
    store = Store(tmp_path)
    seed(store, 2)
    provider = FakeProvider([{"score": 0.3, "rationale": "meh"}, {"score": 0.9, "rationale": "great"}])
    rows = score_leads(store, provider, iep={"roles": ["eng"]})
    assert [r["score"] for r in rows] == [0.9, 0.3]
    index = store.read_index("leads")
    assert all(entry["status"] == "scored" for entry in index.values())
    assert sorted(entry["score"] for entry in index.values()) == [0.3, 0.9]


def test_only_new_skips_scored(tmp_path):
    store = Store(tmp_path)
    leads = seed(store, 2)
    store.set_lead_status(leads[0].id, "scored")
    provider = FakeProvider([{"score": 0.5, "rationale": "ok"}])
    rows = score_leads(store, provider, iep={})
    assert len(rows) == 1


def test_invalid_response_gets_one_reask(tmp_path):
    store = Store(tmp_path)
    seed(store, 1)
    provider = FakeProvider([LLMError("bad json"), {"score": 0.6, "rationale": "ok"}])
    rows = score_leads(store, provider, iep={})
    assert rows[0]["score"] == 0.6
    assert provider.results == []


def test_double_failure_continues_batch(tmp_path):
    store = Store(tmp_path)
    seed(store, 2)
    provider = FakeProvider([LLMError("boom"), LLMError("boom"), {"score": 0.7, "rationale": "ok"}])
    rows = score_leads(store, provider, iep={})
    scores = [r["score"] for r in rows]
    assert 0.7 in scores and None in scores
    index = store.read_index("leads")
    statuses = sorted(entry["status"] for entry in index.values())
    assert statuses == ["new", "scored"]
