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
