from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.matchup_context import parse_bout_date  # noqa: E402
from app.models import FightResult, FighterProfile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit profile records against imported fight-history coverage."
    )
    parser.add_argument("--limit", type=int, default=100, help="Rows to print.")
    parser.add_argument(
        "--min-missing-bouts",
        type=int,
        default=8,
        help="Minimum record-vs-history gap to include.",
    )
    parser.add_argument(
        "--stale-years",
        type=float,
        default=2.0,
        help="Include fighters whose latest imported bout is older than this.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Audit date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument("--csv-out", default=None, help="Optional CSV output path.")
    args = parser.parse_args()

    as_of = parse_bout_date(args.as_of) if args.as_of else datetime.now(timezone.utc).date()
    if as_of is None:
        raise SystemExit("--as-of must be YYYY-MM-DD.")

    init_db()
    with SessionLocal() as db:
        rows = audit_fight_history_freshness(
            db,
            as_of=as_of,
            min_missing_bouts=args.min_missing_bouts,
            stale_years=args.stale_years,
        )

    if args.csv_out:
        write_csv(Path(args.csv_out), rows)

    for row in rows[: args.limit]:
        print(
            f"{row['name']}: record={row['profile_record']} matched={row['matched_bouts']} "
            f"missing={row['missing_bouts']} last={row['last_bout_date']} "
            f"years_ago={row['last_bout_years_ago']}"
        )
    print(f"Flagged fighters: {len(rows)}")


def audit_fight_history_freshness(
    db,
    as_of: date,
    min_missing_bouts: int = 8,
    stale_years: float = 2.0,
) -> list[dict[str, object]]:
    fight_index: dict[str, dict[str, object]] = defaultdict(
        lambda: {"matched_bouts": 0, "last_bout_date": None}
    )
    for result in db.scalars(select(FightResult)).all():
        fought_on = parse_bout_date(result.bout_date)
        for name in (result.winner_name, result.loser_name):
            entry = fight_index[name]
            entry["matched_bouts"] = int(entry["matched_bouts"]) + 1
            if fought_on and (entry["last_bout_date"] is None or fought_on > entry["last_bout_date"]):
                entry["last_bout_date"] = fought_on

    flagged = []
    for profile in db.scalars(select(FighterProfile)).all():
        profile_bouts = int(round(float(profile.wins or 0) + float(profile.losses or 0)))
        entry = fight_index.get(profile.name, {"matched_bouts": 0, "last_bout_date": None})
        matched_bouts = int(entry["matched_bouts"])
        missing_bouts = max(profile_bouts - matched_bouts, 0)
        last_bout_date = entry["last_bout_date"]
        last_bout_years_ago = (
            round(max((as_of - last_bout_date).days / 365.25, 0), 1)
            if last_bout_date is not None
            else None
        )
        stale = last_bout_years_ago is None or last_bout_years_ago >= stale_years
        if missing_bouts < min_missing_bouts and not stale:
            continue
        flagged.append(
            {
                "name": profile.name,
                "profile_record": f"{int(profile.wins)}-{int(profile.losses)}",
                "profile_bouts": profile_bouts,
                "matched_bouts": matched_bouts,
                "missing_bouts": missing_bouts,
                "last_bout_date": last_bout_date.isoformat() if last_bout_date else "",
                "last_bout_years_ago": last_bout_years_ago if last_bout_years_ago is not None else "",
                "source": profile.source,
            }
        )

    flagged.sort(
        key=lambda row: (
            int(row["missing_bouts"]),
            float(row["last_bout_years_ago"] or 999),
            str(row["name"]),
        ),
        reverse=True,
    )
    return flagged


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name",
        "profile_record",
        "profile_bouts",
        "matched_bouts",
        "missing_bouts",
        "last_bout_date",
        "last_bout_years_ago",
        "source",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
