"""Project paths and config loading. All paths are pathlib.Path."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from a2moto.models import ModelSpec

PROJECT_ROOT = Path(os.environ.get("A2MOTO_ROOT", Path(__file__).resolve().parents[2]))

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = PROJECT_ROOT / "logs"

MODELS_YAML = CONFIG_DIR / "models.yaml"
MSRP_HISTORY_YAML = CONFIG_DIR / "msrp_history.yaml"
DB_PATH = DATA_DIR / "listings.db"
UNMATCHED_PATH = DATA_DIR / "unmatched.txt"

# Identify the tool honestly; per-site scrapers reuse this.
USER_AGENT = "a2moto/0.1 (+personal market research tool; respects robots.txt)"

# Default rate limit: 1 request per 2 seconds per domain.
DEFAULT_REQUEST_INTERVAL_S = 2.0


def load_model_specs(path: Path | None = None) -> list[ModelSpec]:
    """Load and validate the model whitelist from models.yaml."""
    yaml_path = path if path is not None else MODELS_YAML
    with yaml_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict) or "models" not in raw:
        raise ValueError(f"{yaml_path} must contain a top-level 'models' list")
    return [ModelSpec.model_validate(entry) for entry in raw["models"]]
