from __future__ import annotations

from pathlib import Path
import json

ODDS_SITES_PATH = Path(__file__).resolve().parent / "data" / "odds_sites_catalog.json"


def load_odds_sites(odds_sites_path: Path = ODDS_SITES_PATH) -> dict[str, object]:
    return json.loads(odds_sites_path.read_text(encoding="utf-8"))
