from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FighterProfile

RANKINGS_PATH = Path(__file__).resolve().parent / "data" / "rankings_catalog.json"


def load_rankings(db: Session, rankings_path: Path = RANKINGS_PATH) -> dict[str, object]:
    catalog = json.loads(rankings_path.read_text(encoding="utf-8"))
    names = {
        entry["name"]
        for promotion in catalog["promotions"]
        for division in promotion.get("divisions", [])
        for entry in division.get("entries", [])
    }
    profiles = {
        profile.name: profile.id
        for profile in db.scalars(select(FighterProfile).where(FighterProfile.name.in_(names))).all()
    }

    enriched = deepcopy(catalog)
    for promotion in enriched["promotions"]:
        promotion["ranked_count"] = sum(
            len(division.get("entries", [])) for division in promotion.get("divisions", [])
        )
        for division in promotion.get("divisions", []):
            for entry in division.get("entries", []):
                entry["fighter_id"] = profiles.get(entry["name"])
    return enriched
