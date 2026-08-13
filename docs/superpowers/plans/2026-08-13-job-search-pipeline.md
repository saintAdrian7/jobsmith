# Job Search Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Python pipeline that sources job leads from three integrations, scores them against an ideal employer profile, and generates per-employer tailored artifacts (resume, cover letter, recommendations) into a filesystem-as-database repo.

**Architecture:** Four data folders (`truth/`, `leads/`, `outputs/`, `outbound/`) hold all state as JSON indexes + markdown artifacts; a `pipeline/` package moves data through them via five CLI commands (`source`, `score`, `generate`, `status`, `mark`). Sources and LLM providers sit behind registries so new ones are one file each.

**Tech Stack:** Python 3.11+, httpx, PyYAML, python-dotenv, pytest. No LLM SDKs (REST via httpx), no DB, no frameworks.

## Global Constraints

Copied from the approved spec — every task's requirements include these; the reviewer gates on them:

1. Simplest approach that fully achieves the goal and scales to it. Complexity only when needed for the desired output.
2. Reusable, cleanly separated components. Each component and function is reliable, independently understandable, independently testable.
3. Readable code. No unnecessary comments. Type hints and one-line contract docstrings only.
4. Built for AI operators as much as humans: machine-readable state, self-describing indexes, predictable CLI contracts.
5. Provider-agnostic LLM layer — not tied to Anthropic.

Repo root: `C:\Users\Admin\Job search`. All paths below are relative to it. Tests never touch the network or require API keys (httpx.MockTransport for HTTP, FakeProvider for LLM). All file writes of state go through `Store` (atomic temp+rename).

---

### Task 1: Scaffold and config loading

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `config.yaml`, `pipeline/__init__.py`, `pipeline/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.load(root: Path) -> Config` with `.data: dict` (parsed config.yaml), `.root: Path`, `.env(name: str) -> str` (raises `ConfigError` naming the missing variable). `class ConfigError(Exception)`.

- [ ] **Step 1: Write scaffold files**

`requirements.txt`:
```
httpx
pyyaml
python-dotenv
pytest
```

`.gitignore`:
```
.env
__pycache__/
*.pyc
.pytest_cache/
```

`.env.example`:
```
ANTHROPIC_API_KEY=
EXA_API_KEY=
APIFY_TOKEN=
MISTRAL_API_KEY=
```

`config.yaml`:
```yaml
llm:
  provider: anthropic          # anthropic | openai_compat
  model: claude-sonnet-5
  api_key_env: ANTHROPIC_API_KEY
  base_url: https://api.mistral.ai/v1   # used by openai_compat only
  max_tokens: 4096

sources:
  ats:
    companies: []              # Greenhouse/Lever board slugs, e.g. [stripe, vercel]
  exa:
    query: ""                  # e.g. "seed-stage startup hiring remote entry-level software engineer"
    num_results: 25
  apify:
    actor: ""                  # e.g. bebity~linkedin-jobs-scraper
    input: {}

generation:
  artifacts: [resume, cover_letter, recommendations]
```

`pipeline/__init__.py`: empty file.

- [ ] **Step 2: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from pipeline.config import Config, ConfigError


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text("llm:\n  provider: anthropic\n", encoding="utf-8")
    return tmp_path


def test_load_reads_yaml(tmp_path):
    config = Config.load(make_root(tmp_path))
    assert config.data["llm"]["provider"] == "anthropic"
    assert config.root == tmp_path


def test_env_returns_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_KEY", "abc")
    config = Config.load(make_root(tmp_path))
    assert config.env("SOME_KEY") == "abc"


def test_env_missing_names_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_KEY", raising=False)
    config = Config.load(make_root(tmp_path))
    with pytest.raises(ConfigError, match="ABSENT_KEY"):
        config.env("ABSENT_KEY")


def test_load_missing_config_fails_fast(tmp_path):
    with pytest.raises(ConfigError, match="config.yaml"):
        Config.load(tmp_path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.config'`

- [ ] **Step 4: Implement**

`pipeline/config.py`:
```python
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class Config:
    root: Path
    data: dict

    @classmethod
    def load(cls, root: Path) -> "Config":
        """Load config.yaml and .env from root; fail fast if config.yaml is absent."""
        path = root / "config.yaml"
        if not path.exists():
            raise ConfigError(f"Missing {path}. Copy config.yaml from the repo root.")
        load_dotenv(root / ".env")
        return cls(root=root, data=yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def env(self, name: str) -> str:
        """Return the environment variable or raise ConfigError naming it."""
        value = os.environ.get(name, "")
        if not value:
            raise ConfigError(f"Missing environment variable: {name}. Add it to .env")
        return value
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore .env.example config.yaml pipeline tests
git commit -m "feat: scaffold and config loading"
```

---

### Task 2: Lead model

**Files:**
- Create: `pipeline/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `@dataclass Lead(company, title, url, source, description="", location="", remote=None, contact_email=None, sourced_at="", score=None, score_rationale="")` with property `id -> str` (16-hex-char sha256 of `"{company.lower()}|{url}"`), `to_dict() -> dict` (includes `id`), `classmethod from_dict(d) -> Lead` (ignores unknown keys), and module function `now_iso() -> str` (UTC ISO-8601 seconds).

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/models.py`:
```python
import hashlib
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp, ISO-8601, second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Lead:
    company: str
    title: str
    url: str
    source: str
    description: str = ""
    location: str = ""
    remote: bool | None = None
    contact_email: str | None = None
    sourced_at: str = ""
    score: float | None = None
    score_rationale: str = ""

    @property
    def id(self) -> str:
        """Deterministic id: sha256 of lowercased company + url, first 16 hex chars."""
        return hashlib.sha256(f"{self.company.lower()}|{self.url}".encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Serialize including the derived id."""
        return {"id": self.id, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        """Deserialize, ignoring unknown keys."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat: Lead model with deterministic id"
```

---

### Task 3: Store (all state IO)

**Files:**
- Create: `pipeline/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Lead`, `now_iso` from `pipeline.models`.
- Produces: `class Store(root: Path)` with:
  - `read_index(folder: str) -> dict` (empty dict if absent)
  - `write_index(folder: str, index: dict) -> None` (atomic)
  - `save_lead(lead: Lead) -> bool` (False and no write if `lead.id` already indexed; else writes `leads/<id>.json` and index entry `{company, title, url, source, score, status: "new", sourced_at}`)
  - `load_lead(lead_id: str) -> Lead`
  - `update_lead(lead: Lead) -> None` (rewrites file; refreshes index entry preserving `status`)
  - `set_lead_status(lead_id: str, status: str) -> None`
  - `save_artifact(lead_id: str, name: str, content: str) -> Path` (writes `outputs/<lead_id>/<name>.md`)
  - `record_output(lead_id: str, company: str, artifacts: list[str]) -> None` (outputs index entry `{company, artifacts, generated_at}`)
  - `read_applications() -> dict`, `mark(lead_id: str, status: str) -> None` (writes `outbound/applications.json`)

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/store.py`:
```python
import json
import os
from pathlib import Path

from pipeline.models import Lead, now_iso


class Store:
    """All reads/writes of pipeline state; the only code that touches index files."""

    def __init__(self, root: Path):
        self.root = root

    def read_index(self, folder: str) -> dict:
        """Return the folder's index.json as a dict, empty if absent."""
        path = self.root / folder / "index.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def write_index(self, folder: str, index: dict) -> None:
        """Atomically replace the folder's index.json."""
        self._write_atomic(self.root / folder / "index.json", json.dumps(index, indent=2))

    def save_lead(self, lead: Lead) -> bool:
        """Persist a new lead; return False without writing if its id is already indexed."""
        index = self.read_index("leads")
        if lead.id in index:
            return False
        lead.sourced_at = lead.sourced_at or now_iso()
        self._write_atomic(self.root / "leads" / f"{lead.id}.json", json.dumps(lead.to_dict(), indent=2))
        index[lead.id] = self._index_entry(lead, status="new")
        self.write_index("leads", index)
        return True

    def load_lead(self, lead_id: str) -> Lead:
        """Read a lead file back into a Lead."""
        data = json.loads((self.root / "leads" / f"{lead_id}.json").read_text(encoding="utf-8"))
        return Lead.from_dict(data)

    def update_lead(self, lead: Lead) -> None:
        """Rewrite a lead's file and refresh its index entry, preserving status."""
        index = self.read_index("leads")
        status = index.get(lead.id, {}).get("status", "new")
        self._write_atomic(self.root / "leads" / f"{lead.id}.json", json.dumps(lead.to_dict(), indent=2))
        index[lead.id] = self._index_entry(lead, status=status)
        self.write_index("leads", index)

    def set_lead_status(self, lead_id: str, status: str) -> None:
        """Update only the status field of a lead's index entry."""
        index = self.read_index("leads")
        index[lead_id]["status"] = status
        self.write_index("leads", index)

    def save_artifact(self, lead_id: str, name: str, content: str) -> Path:
        """Write one generated artifact under outputs/<lead_id>/."""
        path = self.root / "outputs" / lead_id / f"{name}.md"
        self._write_atomic(path, content)
        return path

    def record_output(self, lead_id: str, company: str, artifacts: list[str]) -> None:
        """Index a completed generation for one employer."""
        index = self.read_index("outputs")
        index[lead_id] = {"company": company, "artifacts": artifacts, "generated_at": now_iso()}
        self.write_index("outputs", index)

    def read_applications(self) -> dict:
        """Return the outbound tracker mapping lead_id -> status."""
        path = self.root / "outbound" / "applications.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def mark(self, lead_id: str, status: str) -> None:
        """Set a lead's application status in the outbound tracker."""
        apps = self.read_applications()
        apps[lead_id] = status
        self._write_atomic(self.root / "outbound" / "applications.json", json.dumps(apps, indent=2))

    def _index_entry(self, lead: Lead, status: str) -> dict:
        return {
            "company": lead.company,
            "title": lead.title,
            "url": lead.url,
            "source": lead.source,
            "score": lead.score,
            "status": status,
            "sourced_at": lead.sourced_at,
        }

    def _write_atomic(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/store.py tests/test_store.py
git commit -m "feat: Store with atomic index IO, dedup, artifacts, tracker"
```

---

### Task 4: IEP file and deterministic prefilter

**Files:**
- Create: `iep.yaml`, `pipeline/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Consumes: `Lead` from `pipeline.models`.
- Produces: `passes_must(lead: Lead, must: dict) -> tuple[bool, str]` — `(True, "")` on pass, `(False, reason)` on reject. Also `load_iep(root: Path) -> dict` (parses `iep.yaml`, raises `ConfigError` if absent).

- [ ] **Step 1: Write iep.yaml with the five placeholder criteria**

`iep.yaml`:
```yaml
# Ideal Employer Profile. Fill the five criteria below; the pipeline reads this file.
# `must` rules are enforced deterministically before any LLM call.
# Everything else feeds LLM scoring (pipeline score).

roles:                # 1. Target role titles
  - FILL_ME e.g. software engineer
seniority: FILL_ME    # 2. e.g. entry-level / junior
remote_policy: FILL_ME  # 3. e.g. fully remote, hires from Kenya
company_stage: FILL_ME  # 4. e.g. pre-seed or seed
disqualifiers:        # 5. Instant rejections
  - FILL_ME e.g. requires on-site in US

must:
  remote_required: true
  title_includes_any: []   # empty list = allow any title
  title_excludes: []       # e.g. [senior, staff, principal]
```

- [ ] **Step 2: Write the failing test**

`tests/test_filter.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_filter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`pipeline/filter.py`:
```python
from pathlib import Path

import yaml

from pipeline.config import ConfigError
from pipeline.models import Lead


def load_iep(root: Path) -> dict:
    """Parse iep.yaml at root; fail fast naming the file if absent."""
    path = root / "iep.yaml"
    if not path.exists():
        raise ConfigError(f"Missing {path}. Fill in your ideal employer profile.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def passes_must(lead: Lead, must: dict) -> tuple[bool, str]:
    """Apply deterministic must-rules; return (passed, reason-for-rejection)."""
    title = lead.title.lower()
    if must.get("remote_required") and lead.remote is False:
        return False, f"{lead.company}: not remote"
    includes = [t.lower() for t in must.get("title_includes_any", [])]
    if includes and not any(t in title for t in includes):
        return False, f"{lead.company}: title lacks {includes}"
    excludes = [t.lower() for t in must.get("title_excludes", [])]
    for term in excludes:
        if term in title:
            return False, f"{lead.company}: title contains excluded '{term}'"
    return True, ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_filter.py -v`
Expected: 10 PASS

- [ ] **Step 6: Commit**

```bash
git add iep.yaml pipeline/filter.py tests/test_filter.py
git commit -m "feat: IEP placeholders and deterministic prefilter"
```

---

### Task 5: Source protocol and registry

**Files:**
- Create: `pipeline/sources/__init__.py`
- Test: `tests/test_sources_registry.py`

**Interfaces:**
- Consumes: `Config` from `pipeline.config`, `Lead` from `pipeline.models`.
- Produces: `class SourceUnavailable(Exception)`; `REGISTRY: dict[str, type]` mapping `"ats" | "exa" | "apify"` to source classes (Tasks 6-8 register themselves here by import); `get_source(name: str, config: Config, client: httpx.Client | None = None) -> source instance`. Every source class has `name: str`, `__init__(config: Config, client: httpx.Client | None = None)`, and `fetch(criteria: dict) -> list[Lead]` which raises `SourceUnavailable(reason)` when it cannot run (missing key/config).

- [ ] **Step 1: Write the failing test**

`tests/test_sources_registry.py`:
```python
import pytest

from pipeline.sources import REGISTRY, SourceUnavailable, get_source


def test_registry_has_all_three_sources():
    assert set(REGISTRY) == {"ats", "exa", "apify"}


def test_get_source_unknown_name():
    with pytest.raises(KeyError):
        get_source("nope", config=None)


def test_source_unavailable_is_exception():
    assert issubclass(SourceUnavailable, Exception)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sources_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/sources/__init__.py`:
```python
import httpx

from pipeline.config import Config


class SourceUnavailable(Exception):
    """Raised when a source cannot run (missing key or configuration)."""


REGISTRY: dict[str, type] = {}


def register(cls: type) -> type:
    """Class decorator: add a source class to REGISTRY under its name."""
    REGISTRY[cls.name] = cls
    return cls


def get_source(name: str, config: Config, client: httpx.Client | None = None):
    """Instantiate a registered source by name."""
    return REGISTRY[name](config, client=client)


from pipeline.sources import ats, exa, apify  # noqa: E402,F401  (self-registration)
```

Tasks 6-8 replace these files entirely; for now create identical stubs so the registry import works and the tests pass. `pipeline/sources/ats.py` (and `exa.py`, `apify.py`, changing only the `name` value to `"exa"` / `"apify"`):
```python
from pipeline.sources import SourceUnavailable, register


@register
class Stub:
    name = "ats"

    def __init__(self, config, client=None):
        self.config = config

    def fetch(self, criteria: dict) -> list:
        raise SourceUnavailable("not implemented")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sources_registry.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/sources tests/test_sources_registry.py
git commit -m "feat: source protocol and registry with stubs"
```

---

### Task 6: ATS source (Greenhouse + Lever)

**Files:**
- Modify: `pipeline/sources/ats.py` (replace stub entirely)
- Test: `tests/test_source_ats.py`

**Interfaces:**
- Consumes: `register`, `SourceUnavailable` from `pipeline.sources`; `Lead` from `pipeline.models`; config keys `sources.ats.companies`.
- Produces: `class AtsSource` registered as `"ats"`. `fetch(criteria)` iterates configured company slugs; for each, tries Greenhouse (`https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`) then Lever (`https://api.lever.co/v0/postings/{slug}?mode=json`); normalizes to `Lead`. Raises `SourceUnavailable` if no companies configured. A slug that 404s on both boards is skipped, not fatal.

- [ ] **Step 1: Write the failing test**

`tests/test_source_ats.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_source_ats.py -v`
Expected: FAIL (stub raises SourceUnavailable("not implemented"))

- [ ] **Step 3: Implement**

`pipeline/sources/ats.py` (full replacement):
```python
import httpx

from pipeline.config import Config
from pipeline.models import Lead
from pipeline.sources import SourceUnavailable, register


def _is_remote(location: str) -> bool:
    return "remote" in location.lower()


@register
class AtsSource:
    """Fetch postings from Greenhouse/Lever public board APIs for configured company slugs."""

    name = "ats"

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=20)

    def fetch(self, criteria: dict) -> list[Lead]:
        """Return leads for every configured slug; a slug missing on both boards is skipped."""
        companies = self.config.data.get("sources", {}).get("ats", {}).get("companies", [])
        if not companies:
            raise SourceUnavailable("no companies configured under sources.ats.companies")
        leads: list[Lead] = []
        for slug in companies:
            leads.extend(self._greenhouse(slug) or self._lever(slug))
        return leads

    def _greenhouse(self, slug: str) -> list[Lead]:
        response = self.client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
        if response.status_code != 200:
            return []
        return [
            Lead(
                company=slug,
                title=job["title"],
                url=job["absolute_url"],
                source=self.name,
                description=job.get("content", ""),
                location=job.get("location", {}).get("name", ""),
                remote=_is_remote(job.get("location", {}).get("name", "")),
            )
            for job in response.json().get("jobs", [])
        ]

    def _lever(self, slug: str) -> list[Lead]:
        response = self.client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if response.status_code != 200:
            return []
        return [
            Lead(
                company=slug,
                title=job["text"],
                url=job["hostedUrl"],
                source=self.name,
                description=job.get("descriptionPlain", ""),
                location=job.get("categories", {}).get("location", ""),
                remote=_is_remote(job.get("categories", {}).get("location", "")),
            )
            for job in response.json()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_source_ats.py -v`
Expected: 4 PASS

- [ ] **Step 5: Standalone smoke entry**

Append to `pipeline/sources/ats.py`:
```python
if __name__ == "__main__":
    from pathlib import Path

    leads = AtsSource(Config.load(Path.cwd())).fetch({})
    for lead in leads:
        print(lead.id, lead.company, "-", lead.title)
```

Run: `pytest tests/test_source_ats.py -v` (still 4 PASS)

- [ ] **Step 6: Commit**

```bash
git add pipeline/sources/ats.py tests/test_source_ats.py
git commit -m "feat: ATS source for Greenhouse and Lever"
```

---

### Task 7: Exa source

**Files:**
- Modify: `pipeline/sources/exa.py` (replace stub entirely)
- Test: `tests/test_source_exa.py`

**Interfaces:**
- Consumes: `register`, `SourceUnavailable` from `pipeline.sources`; config keys `sources.exa.query`, `sources.exa.num_results`; env `EXA_API_KEY`.
- Produces: `class ExaSource` registered as `"exa"`. POSTs `https://api.exa.ai/search` with `{"query", "numResults", "contents": {"text": true}}`, header `x-api-key`. Company derived from result URL host (strip `www.`, take first dot-segment). Raises `SourceUnavailable("EXA_API_KEY...")` without a key, or if no query configured.

- [ ] **Step 1: Write the failing test**

`tests/test_source_exa.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_source_exa.py -v`
Expected: FAIL (stub behavior)

- [ ] **Step 3: Implement**

`pipeline/sources/exa.py` (full replacement):
```python
import os
from urllib.parse import urlparse

import httpx

from pipeline.config import Config
from pipeline.models import Lead
from pipeline.sources import SourceUnavailable, register


def _company_from_url(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    return host.split(".")[0]


@register
class ExaSource:
    """Discover postings via Exa semantic web search."""

    name = "exa"

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=30)

    def fetch(self, criteria: dict) -> list[Lead]:
        """Search Exa with the configured query and normalize results to Leads."""
        if not os.environ.get("EXA_API_KEY"):
            raise SourceUnavailable("EXA_API_KEY not set; add it to .env or skip this source")
        settings = self.config.data.get("sources", {}).get("exa", {})
        if not settings.get("query"):
            raise SourceUnavailable("no query configured under sources.exa.query")
        response = self.client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": os.environ["EXA_API_KEY"]},
            json={
                "query": settings["query"],
                "numResults": settings.get("num_results", 25),
                "contents": {"text": True},
            },
        )
        response.raise_for_status()
        return [
            Lead(
                company=_company_from_url(item["url"]),
                title=item.get("title", "") or "Untitled posting",
                url=item["url"],
                source=self.name,
                description=item.get("text", ""),
            )
            for item in response.json().get("results", [])
        ]


if __name__ == "__main__":
    from pathlib import Path

    for lead in ExaSource(Config.load(Path.cwd())).fetch({}):
        print(lead.id, lead.company, "-", lead.title)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_source_exa.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/sources/exa.py tests/test_source_exa.py
git commit -m "feat: Exa search source"
```

---

### Task 8: Apify source

**Files:**
- Modify: `pipeline/sources/apify.py` (replace stub entirely)
- Test: `tests/test_source_apify.py`

**Interfaces:**
- Consumes: `register`, `SourceUnavailable` from `pipeline.sources`; config keys `sources.apify.actor`, `sources.apify.input`; env `APIFY_TOKEN`.
- Produces: `class ApifySource` registered as `"apify"`. POSTs `https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token=...` with the configured input; maps dataset items via `.get` on keys `title`, `company`/`companyName`, `url`/`link`, `location`, `description`. Items without a url are skipped. Raises `SourceUnavailable` on missing token or actor.

- [ ] **Step 1: Write the failing test**

`tests/test_source_apify.py`:
```python
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


def test_missing_token_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(SourceUnavailable, match="APIFY_TOKEN"):
        get_source("apify", make_config(tmp_path)).fetch({})


def test_missing_actor_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")
    with pytest.raises(SourceUnavailable, match="actor"):
        get_source("apify", make_config(tmp_path, actor="")).fetch({})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_source_apify.py -v`
Expected: FAIL (stub behavior)

- [ ] **Step 3: Implement**

`pipeline/sources/apify.py` (full replacement):
```python
import os

import httpx

from pipeline.config import Config
from pipeline.models import Lead
from pipeline.sources import SourceUnavailable, register


@register
class ApifySource:
    """Run a configured Apify actor synchronously and map its dataset items to Leads."""

    name = "apify"

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=120)

    def fetch(self, criteria: dict) -> list[Lead]:
        """Invoke the actor and normalize items; items without a url are skipped."""
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            raise SourceUnavailable("APIFY_TOKEN not set; add it to .env or skip this source")
        settings = self.config.data.get("sources", {}).get("apify", {})
        if not settings.get("actor"):
            raise SourceUnavailable("no actor configured under sources.apify.actor")
        response = self.client.post(
            f"https://api.apify.com/v2/acts/{settings['actor']}/run-sync-get-dataset-items",
            params={"token": token},
            json=settings.get("input", {}),
        )
        response.raise_for_status()
        leads = []
        for item in response.json():
            url = item.get("url") or item.get("link")
            if not url:
                continue
            location = item.get("location", "")
            leads.append(
                Lead(
                    company=item.get("company") or item.get("companyName") or "unknown",
                    title=item.get("title", "Untitled posting"),
                    url=url,
                    source=self.name,
                    description=item.get("description", ""),
                    location=location,
                    remote="remote" in location.lower(),
                )
            )
        return leads


if __name__ == "__main__":
    from pathlib import Path

    for lead in ApifySource(Config.load(Path.cwd())).fetch({}):
        print(lead.id, lead.company, "-", lead.title)
```

- [ ] **Step 4: Run full source suite**

Run: `pytest tests/test_source_apify.py tests/test_sources_registry.py -v`
Expected: all PASS (registry now holds three real sources)

- [ ] **Step 5: Commit**

```bash
git add pipeline/sources/apify.py tests/test_source_apify.py
git commit -m "feat: Apify actor source"
```

---

### Task 9: LLM layer (interface + two providers)

**Files:**
- Create: `pipeline/llm/__init__.py`, `pipeline/llm/anthropic.py`, `pipeline/llm/openai_compat.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `Config` (keys `llm.provider`, `llm.model`, `llm.api_key_env`, `llm.base_url`, `llm.max_tokens`).
- Produces:
  - `class LLMError(Exception)`
  - `get_provider(config: Config, client: httpx.Client | None = None) -> provider` — raises `LLMError` for unknown provider names.
  - Every provider implements `complete(messages: list[dict], json_mode: bool = False) -> str | dict`. `messages` uses `{"role": "system"|"user", "content": str}`. With `json_mode=True` the raw text is parsed as JSON (strip markdown fences first); invalid JSON raises `LLMError`. HTTP 429/5xx retries once after 2s (`time.sleep`), then raises `LLMError`.
  - Providers: `"anthropic"` (POST `https://api.anthropic.com/v1/messages`, headers `x-api-key`, `anthropic-version: 2023-06-01`; system message goes in top-level `system` field) and `"openai_compat"` (POST `{base_url}/chat/completions`, bearer auth; covers Mistral/OpenAI/Groq/Ollama).

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:
```python
import httpx
import pytest

from pipeline.config import Config
from pipeline.llm import LLMError, get_provider

ANTHROPIC_BODY = {"content": [{"type": "text", "text": '{"score": 0.8}'}]}
OPENAI_BODY = {"choices": [{"message": {"content": "hello"}}]}


def make_config(tmp_path, provider, api_key_env="ANTHROPIC_API_KEY"):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    config = Config.load(tmp_path)
    config.data = {
        "llm": {
            "provider": provider,
            "model": "m",
            "api_key_env": api_key_env,
            "base_url": "https://api.example.com/v1",
            "max_tokens": 100,
        }
    }
    return config


def client_returning(status, body):
    def handler(request):
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_anthropic_extracts_text_and_system_field(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    captured = {}

    def handler(request):
        import json

        captured.update(json.loads(request.content))
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
    assert provider.complete(messages) == '{"score": 0.8}'
    assert captured["system"] == "be brief"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]


def test_json_mode_parses_and_strips_fences(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    body = {"content": [{"type": "text", "text": '```json\n{"a": 1}\n```'}]}
    provider = get_provider(make_config(tmp_path, "anthropic"), client=client_returning(200, body))
    assert provider.complete([{"role": "user", "content": "x"}], json_mode=True) == {"a": 1}


def test_openai_compat_extracts_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    provider = get_provider(
        make_config(tmp_path, "openai_compat", api_key_env="MISTRAL_API_KEY"),
        client=client_returning(200, OPENAI_BODY),
    )
    assert provider.complete([{"role": "user", "content": "hi"}]) == "hello"


def test_server_error_retries_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={})

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMError):
        provider.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 2


def test_unknown_provider_raises(tmp_path):
    with pytest.raises(LLMError, match="unknown"):
        get_provider(make_config(tmp_path, "unknown"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/llm/__init__.py`:
```python
import json
import time

import httpx

from pipeline.config import Config


class LLMError(Exception):
    """Raised on provider failures or unparseable model output."""


class BaseProvider:
    """Shared request/retry/JSON plumbing; subclasses define _request and _extract."""

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.settings = config.data.get("llm", {})
        self.api_key = config.env(self.settings.get("api_key_env", "ANTHROPIC_API_KEY"))
        self.client = client or httpx.Client(timeout=120)

    def complete(self, messages: list[dict], json_mode: bool = False) -> str | dict:
        """Run one completion; with json_mode, parse the reply as JSON or raise LLMError."""
        response = self._request(messages)
        if response.status_code in (429,) or response.status_code >= 500:
            time.sleep(2)
            response = self._request(messages)
        if response.status_code != 200:
            raise LLMError(f"{self.__class__.__name__}: HTTP {response.status_code}: {response.text[:200]}")
        text = self._extract(response.json())
        return _parse_json(text) if json_mode else text

    def _request(self, messages: list[dict]) -> httpx.Response:
        raise NotImplementedError

    def _extract(self, body: dict) -> str:
        raise NotImplementedError


def _parse_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"model returned invalid JSON: {e}") from e


def get_provider(config: Config, client: httpx.Client | None = None) -> BaseProvider:
    """Instantiate the provider named in config llm.provider."""
    from pipeline.llm.anthropic import AnthropicProvider
    from pipeline.llm.openai_compat import OpenAICompatProvider

    providers = {"anthropic": AnthropicProvider, "openai_compat": OpenAICompatProvider}
    name = config.data.get("llm", {}).get("provider", "anthropic")
    if name not in providers:
        raise LLMError(f"unknown provider '{name}'; choose from {sorted(providers)}")
    return providers[name](config, client=client)
```

`pipeline/llm/anthropic.py`:
```python
import httpx

from pipeline.llm import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API over REST."""

    def _request(self, messages: list[dict]) -> httpx.Response:
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        payload = {
            "model": self.settings.get("model", "claude-sonnet-5"),
            "max_tokens": self.settings.get("max_tokens", 4096),
            "messages": [m for m in messages if m["role"] != "system"],
        }
        if system:
            payload["system"] = system
        return self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json=payload,
        )

    def _extract(self, body: dict) -> str:
        return "".join(block["text"] for block in body["content"] if block["type"] == "text")
```

`pipeline/llm/openai_compat.py`:
```python
import httpx

from pipeline.llm import BaseProvider


class OpenAICompatProvider(BaseProvider):
    """Any OpenAI-compatible chat/completions endpoint (Mistral, OpenAI, Groq, Ollama)."""

    def _request(self, messages: list[dict]) -> httpx.Response:
        return self.client.post(
            f"{self.settings.get('base_url', '').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.settings.get("model", ""),
                "max_tokens": self.settings.get("max_tokens", 4096),
                "messages": messages,
            },
        )

    def _extract(self, body: dict) -> str:
        return body["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm tests/test_llm.py
git commit -m "feat: provider-agnostic LLM layer with anthropic and openai_compat"
```

---

### Task 10: Scoring stage

**Files:**
- Create: `pipeline/score.py`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `Store`, `Lead`, provider objects with `complete(messages, json_mode)` (Task 9), `load_iep` (Task 4).
- Produces: `score_leads(store: Store, provider, iep: dict, only_new: bool = True) -> list[dict]` — for each lead in `leads/index.json` with status `"new"` (or all statuses when `only_new=False`), calls the provider with the IEP + lead, expects `{"score": float, "rationale": str}`, writes score onto the lead (`update_lead`) and sets status `"scored"`. Returns summary rows `{"id", "company", "score"}` sorted descending by score. Invalid or failed responses get exactly one re-ask (spec requirement); a lead that fails both attempts is reported with `"score": None`, left in its prior status, and the batch continues.

- [ ] **Step 1: Write the failing test**

`tests/test_score.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_score.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/score.py`:
```python
import json

import yaml

from pipeline.llm import LLMError
from pipeline.store import Store

SYSTEM = (
    "You evaluate a job lead against a candidate's ideal employer profile. "
    'Respond with JSON only: {"score": <float 0..1>, "rationale": "<one sentence>"}'
)


def score_leads(store: Store, provider, iep: dict, only_new: bool = True) -> list[dict]:
    """Score unscored leads against the IEP; returns {id, company, score} rows, best first."""
    index = store.read_index("leads")
    rows = []
    for lead_id, entry in index.items():
        if only_new and entry["status"] != "new":
            continue
        lead = store.load_lead(lead_id)
        try:
            result = _ask_with_one_retry(provider, iep, lead)
            lead.score = float(result["score"])
            lead.score_rationale = str(result.get("rationale", ""))
            store.update_lead(lead)
            store.set_lead_status(lead_id, "scored")
            rows.append({"id": lead_id, "company": lead.company, "score": lead.score})
        except (LLMError, KeyError, TypeError, ValueError) as e:
            rows.append({"id": lead_id, "company": lead.company, "score": None, "error": str(e)})
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


def _ask_with_one_retry(provider, iep: dict, lead) -> dict:
    """One scoring call with a single re-ask on failure, per spec."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"PROFILE:\n{yaml.safe_dump(iep)}\nLEAD:\n{json.dumps(lead.to_dict())}",
        },
    ]
    try:
        return provider.complete(messages, json_mode=True)
    except LLMError:
        return provider.complete(messages, json_mode=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_score.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/score.py tests/test_score.py
git commit -m "feat: LLM scoring stage against IEP"
```

---

### Task 11: Generation stage

**Files:**
- Create: `pipeline/generate.py`
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `Store` (Task 3), provider `.complete` (Task 9), config key `generation.artifacts`.
- Produces:
  - `load_truth(root: Path) -> str` — concatenates `truth/resume.md`, `truth/facts.yaml`, and every file in `truth/writing/`, each preceded by a `## <filename>` header line. Raises `ConfigError` if `truth/resume.md` is missing.
  - `generate_for(lead_id: str, store: Store, provider, truth: str, artifacts: list[str], force: bool = False) -> list[Path]` — one `complete()` call per artifact name using `PROMPTS[name]`; writes each via `store.save_artifact`; records the output (`store.record_output`), sets lead status `"generated"`, and marks the application tracker `"generated"` (`store.mark`). Raises `FileExistsError` if the output folder already has files and `force` is False.
  - `PROMPTS: dict[str, str]` with keys `resume`, `cover_letter`, `recommendations`.

- [ ] **Step 1: Write the failing test**

`tests/test_generate.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_generate.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/generate.py`:
```python
import json
from pathlib import Path

from pipeline.config import ConfigError
from pipeline.store import Store

PROMPTS = {
    "resume": (
        "Tailor the candidate's resume to this specific job lead. Keep every fact truthful to "
        "the TRUTH section; reorder and reword for relevance to the lead. Output markdown only."
    ),
    "cover_letter": (
        "Write a cover letter for this lead in the candidate's own voice (see writing samples in "
        "TRUTH). Specific, warm, no clichés, under 300 words. Output markdown only."
    ),
    "recommendations": (
        "Given the lead's likely tech stack and the candidate's skills, recommend: 2-3 open source "
        "repositories worth contributing to (with what kind of PR), and 3 practice problems or "
        "topics to sharpen relevant skills. Output markdown with two sections."
    ),
}


def load_truth(root: Path) -> str:
    """Concatenate truth/ files into one context block; resume.md is required."""
    truth_dir = root / "truth"
    resume = truth_dir / "resume.md"
    if not resume.exists():
        raise ConfigError(f"Missing {resume}. Add your resume before generating.")
    parts = []
    for path in [resume, truth_dir / "facts.yaml", *sorted((truth_dir / "writing").glob("*"))]:
        if path.exists() and path.is_file():
            parts.append(f"## {path.name}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def generate_for(
    lead_id: str,
    store: Store,
    provider,
    truth: str,
    artifacts: list[str],
    force: bool = False,
) -> list[Path]:
    """Generate all artifacts for one lead; refuse to overwrite existing output without force."""
    output_dir = store.root / "outputs" / lead_id
    if not force and output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"{output_dir} already has artifacts; rerun with --force to regenerate")
    lead = store.load_lead(lead_id)
    context = f"TRUTH:\n{truth}\n\nLEAD:\n{json.dumps(lead.to_dict(), indent=2)}"
    paths = []
    for name in artifacts:
        content = provider.complete(
            [
                {"role": "system", "content": PROMPTS[name]},
                {"role": "user", "content": context},
            ]
        )
        paths.append(store.save_artifact(lead_id, name, content))
    store.record_output(lead_id, lead.company, artifacts)
    store.set_lead_status(lead_id, "generated")
    store.mark(lead_id, "generated")
    return paths
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_generate.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/generate.py tests/test_generate.py
git commit -m "feat: per-employer artifact generation"
```

---

### Task 12: CLI wiring all five commands

**Files:**
- Create: `pipeline/cli.py`, `pipeline/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above — `Config.load`, `Store`, `REGISTRY`/`get_source`/`SourceUnavailable`, `passes_must`/`load_iep`, `get_provider`, `score_leads`, `load_truth`/`generate_for`.
- Produces: `main(argv: list[str] | None = None, root: Path | None = None) -> int` (0 success, 1 on `ConfigError`). Commands:
  - `source [--source NAME]` — fetch from one or all sources; prefilter with `passes_must`; dedup via `store.save_lead`; print per-source summary lines `"{name}: sourced N, filtered M, duplicate K"` or `"{name}: skipped - {reason}"` or `"{name}: failed - {error}"`.
  - `score [--all]` — score new leads (all with `--all`); print `"{score} {company} {id}"` rows.
  - `generate (LEAD_ID | --top N) [--force]` — generate for one lead or the N best-scored leads with status `"scored"`.
  - `status` — print counts: leads by status, outputs total, applications by status.
  - `mark LEAD_ID STATUS` — where STATUS is one of `generated|applied|replied|rejected`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`pipeline/cli.py`:
```python
import argparse
from pathlib import Path

from pipeline.config import Config, ConfigError
from pipeline.filter import load_iep, passes_must
from pipeline.generate import generate_for, load_truth
from pipeline.llm import get_provider
from pipeline.score import score_leads
from pipeline.sources import REGISTRY, SourceUnavailable
from pipeline.store import Store


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Entry point for python -m pipeline; returns process exit code."""
    args = _parse(argv)
    root = root or Path.cwd()
    try:
        config = Config.load(root)
        store = Store(root)
        {
            "source": lambda: _source(args, config, store, root),
            "score": lambda: _score(args, config, store, root),
            "generate": lambda: _generate(args, config, store, root),
            "status": lambda: _status(store),
            "mark": lambda: store.mark(args.lead_id, args.status),
        }[args.command]()
        return 0
    except ConfigError as e:
        print(e)
        return 1


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source", help="fetch leads from sources")
    source.add_argument("--source", choices=sorted(REGISTRY), default=None)
    score = commands.add_parser("score", help="LLM-score leads against iep.yaml")
    score.add_argument("--all", action="store_true")
    generate = commands.add_parser("generate", help="generate artifacts for leads")
    generate.add_argument("lead_id", nargs="?", default=None)
    generate.add_argument("--top", type=int, default=None)
    generate.add_argument("--force", action="store_true")
    commands.add_parser("status", help="show pipeline state counts")
    mark = commands.add_parser("mark", help="set application status")
    mark.add_argument("lead_id")
    mark.add_argument("status", choices=["generated", "applied", "replied", "rejected"])
    return parser.parse_args(argv)


def _source(args, config: Config, store: Store, root: Path) -> None:
    iep = load_iep(root)
    must = iep.get("must", {})
    names = [args.source] if args.source else sorted(REGISTRY)
    for name in names:
        try:
            leads = REGISTRY[name](config).fetch(iep)
        except SourceUnavailable as e:
            print(f"{name}: skipped - {e}")
            continue
        except Exception as e:
            print(f"{name}: failed - {e}")
            continue
        sourced = filtered = duplicate = 0
        for lead in leads:
            passed, _ = passes_must(lead, must)
            if not passed:
                filtered += 1
            elif store.save_lead(lead):
                sourced += 1
            else:
                duplicate += 1
        print(f"{name}: sourced {sourced}, filtered {filtered}, duplicate {duplicate}")


def _score(args, config: Config, store: Store, root: Path) -> None:
    rows = score_leads(store, get_provider(config), load_iep(root), only_new=not args.all)
    for row in rows:
        print(f"{row['score']} {row['company']} {row['id']}" + (f"  error: {row['error']}" if row.get("error") else ""))


def _generate(args, config: Config, store: Store, root: Path) -> None:
    if not args.lead_id and not args.top:
        raise ConfigError("generate needs a LEAD_ID or --top N")
    truth = load_truth(root)
    provider = get_provider(config)
    artifacts = config.data.get("generation", {}).get("artifacts", ["resume", "cover_letter", "recommendations"])
    if args.lead_id:
        ids = [args.lead_id]
    else:
        scored = [
            (entry["score"], lead_id)
            for lead_id, entry in store.read_index("leads").items()
            if entry["status"] == "scored" and entry["score"] is not None
        ]
        ids = [lead_id for _, lead_id in sorted(scored, reverse=True)[: args.top]]
    for lead_id in ids:
        paths = generate_for(lead_id, store, provider, truth, artifacts, force=args.force)
        print(f"{lead_id}: wrote {', '.join(p.name for p in paths)}")


def _status(store: Store) -> None:
    leads = store.read_index("leads")
    by_status: dict[str, int] = {}
    for entry in leads.values():
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1
    print(f"leads: {len(leads)} {by_status}")
    print(f"outputs: {len(store.read_index('outputs'))}")
    apps: dict[str, int] = {}
    for status in store.read_applications().values():
        apps[status] = apps.get(status, 0) + 1
    print(f"applications: {apps}")
```

`pipeline/__main__.py`:
```python
import sys

from pipeline.cli import main

sys.exit(main())
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: all tests from Tasks 1-12 PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/cli.py pipeline/__main__.py tests/test_cli.py
git commit -m "feat: CLI with source, score, generate, status, mark"
```

---

### Task 13: Data folders, indexes, CLAUDE.md, README

**Files:**
- Create: `truth/INDEX.md`, `truth/resume.md`, `truth/facts.yaml`, `truth/writing/.gitkeep`, `leads/INDEX.md`, `outputs/INDEX.md`, `outbound/INDEX.md`, `CLAUDE.md`, `README.md`

**Interfaces:**
- Consumes: the working CLI (Task 12) — README commands must match `pipeline/cli.py` exactly.
- Produces: the self-describing repo an agent can operate from `CLAUDE.md` + `INDEX.md` files alone.

- [ ] **Step 1: Write the data-folder files**

`truth/INDEX.md`:
```markdown
# truth/ — source of truth (module 1)

Everything the pipeline knows about the candidate. Consumed whole by `pipeline generate`.

| File | Purpose |
|---|---|
| resume.md | Starter resume, markdown. REQUIRED before generating. |
| facts.yaml | Structured facts: skills, links, work authorization, constraints. |
| writing/ | Past cover letters and posts — voice samples for tone matching. |

No index.json here: this folder is read in full, not queried by id.
```

`truth/resume.md`:
```markdown
# FILL_ME — Your Name

Replace this file with your real resume in markdown.
```

`truth/facts.yaml`:
```yaml
# Structured facts the generator may cite. Fill in.
name: FILL_ME
location: FILL_ME
links:
  github: FILL_ME
  linkedin: FILL_ME
skills: []
work_authorization: FILL_ME
constraints: []   # e.g. "remote only", "timezone UTC+3"
```

`leads/INDEX.md`:
```markdown
# leads/ — sourced employers (module 2)

Written by `pipeline source` and `pipeline score`.

- `index.json`: lead_id -> {company, title, url, source, score, status, sourced_at}
- `<lead_id>.json`: full Lead record (see pipeline/models.py)

Statuses: new (sourced) -> scored (has score 0-1) -> generated (artifacts exist).
lead_id = first 16 hex chars of sha256("company|url") — deterministic, dedup key.
```

`outputs/INDEX.md`:
```markdown
# outputs/ — per-employer artifacts (module 3)

Written by `pipeline generate`.

- `index.json`: lead_id -> {company, artifacts: [names], generated_at}
- `<lead_id>/resume.md`, `cover_letter.md`, `recommendations.md`

Never overwritten without `--force`.
```

`outbound/INDEX.md`:
```markdown
# outbound/ — application tracking (module 4)

- `applications.json`: lead_id -> generated | applied | replied | rejected

v1 tracks only; sending is out of scope. Update with `pipeline mark <lead_id> <status>`.
```

- [ ] **Step 2: Write CLAUDE.md**

`CLAUDE.md`:
```markdown
# Job Search Pipeline — Operator Manual

A standalone pipeline: sources job leads, scores them against an ideal employer
profile, generates tailored artifacts per employer. State is files; every data
folder has an INDEX.md describing its schema.

## Modules and flow

truth/ (candidate data) + leads/ (sourced employers) -> outputs/ (artifacts) -> outbound/ (tracking)

Code lives in pipeline/. Stages communicate only via files, so any stage can rerun independently.

## Commands

    python -m pipeline source [--source ats|exa|apify]
    python -m pipeline score [--all]
    python -m pipeline generate <lead_id> | --top N [--force]
    python -m pipeline status
    python -m pipeline mark <lead_id> <generated|applied|replied|rejected>

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill keys you have (ATS source needs none).
3. Fill `iep.yaml` (five criteria + must-rules), `truth/resume.md`, `truth/facts.yaml`.
4. Add company slugs / query / actor in `config.yaml`.

## Extending

- New source: one file in pipeline/sources/ implementing fetch(criteria) -> list[Lead],
  decorated with @register. Missing prerequisites raise SourceUnavailable.
- New LLM provider: subclass BaseProvider in pipeline/llm/, add to get_provider's dict.
- Outbound sending: new module consuming outbound/applications.json entries with
  status "generated". Not built in v1 by design.

## Constraints (binding for all code changes; reviewers gate on these)

1. Simplest approach that fully achieves the goal and scales to it.
2. Reusable, cleanly separated, independently testable components.
3. Readable code; type hints and one-line contract docstrings; no other comments.
4. Machine-readable state and predictable interfaces — built for AI operators too.
5. LLM layer stays provider-agnostic.

## Testing

`pytest` — no network, no keys. Sources use httpx.MockTransport fixtures; LLM
tests use fakes. Every component is also runnable standalone (sources via
`python -m pipeline.sources.<name>`).
```

- [ ] **Step 3: Write README.md**

`README.md`:
```markdown
# Job Search Pipeline

Four-module job application system: a structured source of truth, lead sourcing
against an ideal employer profile (IEP), per-employer tailored outputs, and
application tracking.

    truth/ ──┐
             ├──> outputs/<lead_id>/ (resume, cover letter, recommendations)
    leads/ ──┘         │
    (source + score)   └──> outbound/applications.json

## Quick start

    pip install -r requirements.txt
    copy .env.example .env        # fill the keys you have; ATS needs none
    # fill iep.yaml, truth/resume.md, truth/facts.yaml, config.yaml
    python -m pipeline source
    python -m pipeline score
    python -m pipeline generate --top 5
    python -m pipeline status

## Design

- Filesystem as database: JSON indexes + markdown artifacts, all state inspectable.
- Three lead sources (Greenhouse/Lever ATS APIs, Exa search, Apify actors) behind
  one interface; each independently runnable and testable; missing keys skip cleanly.
- Provider-agnostic LLM layer: Anthropic or any OpenAI-compatible API (Mistral,
  Groq, Ollama) — switch in config.yaml.
- See CLAUDE.md for the operator manual and docs/superpowers/specs/ for the design.

## Tests

    pytest
```

- [ ] **Step 4: Verify suite still green and status runs in repo root**

Run: `pytest -q` — expected: all PASS.
Run: `python -m pipeline status` — expected: `leads: 0 {}` / `outputs: 0` / `applications: {}` (empty state, exit 0).

- [ ] **Step 5: Commit**

```bash
git add truth leads outputs outbound CLAUDE.md README.md
git commit -m "feat: data folders, indexes, operator manual"
```

---

## Review rubric (applies to every task)

The reviewer checks, in order:
1. **Works:** the task's tests pass (`pytest`), and the full suite passes.
2. **Constraint 1:** no speculative abstraction, no unused parameters, no features beyond the task.
3. **Constraint 2:** the component is testable in isolation and touches only its declared interfaces.
4. **Constraint 3:** no comments beyond one-line contract docstrings; type hints present.
5. **Constraint 4:** any state it writes is JSON/markdown documented in an INDEX.md.
6. **Constraint 5:** nothing outside `pipeline/llm/` imports provider-specific anything.

Fail any check → return to builder with specific findings.
