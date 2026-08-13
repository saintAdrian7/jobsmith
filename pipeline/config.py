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
