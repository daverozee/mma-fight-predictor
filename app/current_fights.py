from __future__ import annotations

from csv import DictReader
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FightResult, FighterProfile

CURRENT_FIGHT_RESULTS_PATH = Path(__file__).resolve().parent / "data" / "current_fight_results.csv"
CURRENT_FIGHT_SOURCE = "curated-current-results"


def import_current_fight_results(
    db: Session,
    csv_path: Path = CURRENT_FIGHT_RESULTS_PATH,
    source: str = CURRENT_FIGHT_SOURCE,
) -> int:
    if not csv_path.exists():
        return 0

    profiles = {profile.name: profile.id for profile in db.scalars(select(FighterProfile)).all()}
    imported = 0
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        for row in DictReader(file):
            winner_name = clean(row.get("winner_name"))
            loser_name = clean(row.get("loser_name"))
            event_name = clean(row.get("event_name"))
            bout_date = clean(row.get("bout_date"))
            if not winner_name or not loser_name or not event_name or not bout_date:
                continue
            existing = db.scalar(
                select(FightResult).where(
                    FightResult.winner_name == winner_name,
                    FightResult.loser_name == loser_name,
                    FightResult.event_name == event_name,
                    FightResult.bout_date == bout_date,
                )
            )
            if existing:
                continue
            db.add(
                FightResult(
                    winner_profile_id=profiles.get(winner_name),
                    loser_profile_id=profiles.get(loser_name),
                    winner_name=winner_name,
                    loser_name=loser_name,
                    event_name=event_name,
                    bout_date=bout_date,
                    method=clean(row.get("method")),
                    source=source,
                    source_url=clean(row.get("source_url")),
                )
            )
            imported += 1
    db.commit()
    return imported


def clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None
