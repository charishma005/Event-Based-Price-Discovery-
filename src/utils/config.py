from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    # Environment variables still work; python-dotenv is installed by requirements.txt.
    pass


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a project YAML file without interpreting provider credentials."""
    with Path(path).open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    return value or {}


def settings() -> dict[str, Any]:
    return load_yaml(PROJECT_ROOT / "config" / "settings.yaml")
