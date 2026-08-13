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
