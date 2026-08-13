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
