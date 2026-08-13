from pipeline.models import Lead, now_iso


def make_lead(**overrides) -> Lead:
    base = dict(company="Acme", title="Engineer", url="https://acme.dev/j/1", source="ats")
    base.update(overrides)
    return Lead(**base)


def test_id_is_deterministic_and_case_insensitive_on_company():
    assert make_lead().id == make_lead(company="ACME").id
    assert len(make_lead().id) == 16


def test_id_changes_with_url():
    assert make_lead().id != make_lead(url="https://acme.dev/j/2").id


def test_round_trip_preserves_fields_and_ignores_unknown_keys():
    lead = make_lead(remote=True, score=0.8)
    data = lead.to_dict()
    assert data["id"] == lead.id
    data["unknown_field"] = "x"
    restored = Lead.from_dict(data)
    assert restored == lead


def test_now_iso_shape():
    stamp = now_iso()
    assert "T" in stamp and len(stamp) >= 19
