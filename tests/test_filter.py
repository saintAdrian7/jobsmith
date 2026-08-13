import pytest

from pipeline.config import ConfigError
from pipeline.filter import load_iep, passes_must
from pipeline.models import Lead


def make_lead(**overrides) -> Lead:
    base = dict(company="Acme", title="Software Engineer", url="https://a.co/1", source="ats")
    base.update(overrides)
    return Lead(**base)


CASES = [
    ({"remote_required": True}, dict(remote=False), False, "not remote"),
    ({"remote_required": True}, dict(remote=None), True, ""),
    ({"remote_required": True}, dict(remote=True), True, ""),
    ({"title_includes_any": ["engineer"]}, dict(title="Software Engineer"), True, ""),
    ({"title_includes_any": ["designer"]}, dict(title="Software Engineer"), False, "title"),
    ({"title_includes_any": []}, dict(title="Anything"), True, ""),
    ({"title_excludes": ["senior"]}, dict(title="Senior Engineer"), False, "title"),
    ({}, dict(), True, ""),
]


@pytest.mark.parametrize("must,fields,expected,reason_part", CASES)
def test_passes_must(must, fields, expected, reason_part):
    passed, reason = passes_must(make_lead(**fields), must)
    assert passed is expected
    assert reason_part in reason


def test_load_iep(tmp_path):
    (tmp_path / "iep.yaml").write_text("must:\n  remote_required: true\n", encoding="utf-8")
    assert load_iep(tmp_path)["must"]["remote_required"] is True


def test_load_iep_missing(tmp_path):
    with pytest.raises(ConfigError, match="iep.yaml"):
        load_iep(tmp_path)
