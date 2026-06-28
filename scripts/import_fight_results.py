from pathlib import Path
import argparse
import csv
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import FightResult, FighterProfile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import winner-loser fight result edges.")
    parser.add_argument("csv_path", help="CSV with winner_name and loser_name columns.")
    parser.add_argument("--source", default="csv-fight-results")
    parser.add_argument("--source-url", default=None)
    args = parser.parse_args()

    init_db()
    path = Path(args.csv_path)
    imported = 0
    with SessionLocal() as db, path.open("r", encoding="utf-8") as file:
        profiles = {
            row.name: row.id
            for row in db.scalars(select(FighterProfile)).all()
        }
        for row in csv.DictReader(file):
            winner = (row.get("winner_name") or "").strip()
            loser = (row.get("loser_name") or "").strip()
            if not winner or not loser:
                continue
            existing = db.scalar(
                select(FightResult).where(
                    FightResult.winner_name == winner,
                    FightResult.loser_name == loser,
                    FightResult.event_name == blank_to_none(row.get("event_name")),
                    FightResult.bout_date == blank_to_none(row.get("bout_date")),
                    FightResult.source == args.source,
                )
            )
            if existing:
                continue
            db.add(
                FightResult(
                    winner_profile_id=profiles.get(winner),
                    loser_profile_id=profiles.get(loser),
                    winner_name=winner,
                    loser_name=loser,
                    event_name=blank_to_none(row.get("event_name")),
                    bout_date=blank_to_none(row.get("bout_date")),
                    method=blank_to_none(row.get("method")),
                    source=args.source,
                    source_url=args.source_url,
                )
            )
            imported += 1
            if imported % 500 == 0:
                db.commit()
        db.commit()
    print(f"Fight result edges imported: {imported}")


def blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


if __name__ == "__main__":
    main()
