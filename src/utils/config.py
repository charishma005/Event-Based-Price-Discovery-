from __future__ import annotations

import os
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


def raw_databento_dirs() -> list[Path]:
    """Directories searched for immutable Databento files.

    The first entry is the project's own cache and the only place new downloads
    are written. ``T3_EXTRA_RAW_DIRS`` (``os.pathsep``-separated; relative paths
    are resolved against the project root) adds read-only caches, for example a
    raw folder kept outside the repository, so existing files are reused rather
    than copied or downloaded twice.
    """
    primary = PROJECT_ROOT / "data" / "raw" / "databento"
    directories = [primary]
    for item in os.getenv("T3_EXTRA_RAW_DIRS", "").split(os.pathsep):
        item = item.strip()
        if not item:
            continue
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        if path.is_dir() and path not in directories:
            directories.append(path)
    return directories


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a project YAML file without interpreting provider credentials."""
    with Path(path).open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    return value or {}


def settings() -> dict[str, Any]:
    return load_yaml(PROJECT_ROOT / "config" / "settings.yaml")
