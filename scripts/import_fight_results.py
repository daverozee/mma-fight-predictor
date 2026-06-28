from pathlib import Path
import argparse
import csv
import io
import sys
import urllib.request

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import FightResult, FighterProfile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import winner-loser fight result edges.")
    parser.add_argument("csv_path", help="Local path or URL for the bout-history CSV.")
    parser.add_argument(
        "--format",
        choices=["winner-loser", "ufcstats-event-fight-stats"],
        default="winner-loser",
        help="Input format to normalize into winner-loser edges.",
    )
    parser.add_argument("--winner-column", default="winner_name")
    parser.add_argument("--loser-column", default="loser_name")
    parser.add_argument("--event-column", default="event_name")
    parser.add_argument("--date-column", default="bout_date")
    parser.add_argument("--method-column", default="method")
    parser.add_argument(
        "--events-csv",
        default=None,
        help="Companion event CSV path or URL for ufcstats-event-fight-stats imports.",
    )
    parser.add_argument("--source", default="csv-fight-results")
    parser.add_argument("--source-url", default=None)
    parser.add_argument(
        "--allow-source-duplicates",
        action="store_true",
        help="Allow the same bout identity to be imported again under a different source.",
    )
    args = parser.parse_args()

    init_db()
    imported = 0
    skipped = 0
    events = (
        load_ufcstats_events(args.events_csv)
        if args.format == "ufcstats-event-fight-stats"
        else {}
    )
    with SessionLocal() as db:
        profiles = {
            row.name: row.id
            for row in db.scalars(select(FighterProfile)).all()
        }
        for row in csv.DictReader(open_text(args.csv_path)):
            edge = normalize_edge(row, args, events)
            if edge is None:
                skipped += 1
                continue
            existing = db.scalar(
                existing_result_query(edge, args.allow_source_duplicates, args.source)
            )
            if existing:
                skipped += 1
                continue
            db.add(
                FightResult(
                    winner_profile_id=profiles.get(edge["winner_name"]),
                    loser_profile_id=profiles.get(edge["loser_name"]),
                    winner_name=edge["winner_name"],
                    loser_name=edge["loser_name"],
                    event_name=edge["event_name"],
                    bout_date=edge["bout_date"],
                    method=edge["method"],
                    source=args.source,
                    source_url=edge["source_url"] or args.source_url,
                )
            )
            imported += 1
            if imported % 500 == 0:
                db.commit()
        db.commit()
    print(f"Fight result edges imported: {imported}")
    print(f"Rows skipped: {skipped}")


def existing_result_query(
    edge: dict[str, str | None],
    allow_source_duplicates: bool,
    source: str,
):
    query = select(FightResult).where(
        FightResult.winner_name == edge["winner_name"],
        FightResult.loser_name == edge["loser_name"],
        FightResult.event_name == edge["event_name"],
        FightResult.bout_date == edge["bout_date"],
    )
    if allow_source_duplicates:
        query = query.where(FightResult.source == source)
    return query


def normalize_edge(
    row: dict[str, str],
    args: argparse.Namespace,
    events: dict[str, dict[str, str | None]],
) -> dict[str, str | None] | None:
    if args.format == "ufcstats-event-fight-stats":
        return normalize_ufcstats_event_fight_stats(row, events)

    winner = blank_to_none(row.get(args.winner_column))
    loser = blank_to_none(row.get(args.loser_column))
    if not winner or not loser:
        return None

    return {
        "winner_name": winner,
        "loser_name": loser,
        "event_name": blank_to_none(row.get(args.event_column)),
        "bout_date": blank_to_none(row.get(args.date_column)),
        "method": blank_to_none(row.get(args.method_column)),
        "source_url": None,
    }


def normalize_ufcstats_event_fight_stats(
    row: dict[str, str],
    events: dict[str, dict[str, str | None]],
) -> dict[str, str | None] | None:
    result = blank_to_none(row.get("result"))
    if result in {None, "d", "nc"}:
        return None

    f1_id = blank_to_none(row.get("f1_id"))
    f2_id = blank_to_none(row.get("f2_id"))
    f1_name = blank_to_none(row.get("f1_name"))
    f2_name = blank_to_none(row.get("f2_name"))
    if not f1_id or not f2_id or not f1_name or not f2_name:
        return None

    if result == f1_id:
        winner = f1_name
        loser = f2_name
    elif result == f2_id:
        winner = f2_name
        loser = f1_name
    else:
        return None

    event = events.get(blank_to_none(row.get("event_url")) or "", {})
    return {
        "winner_name": winner,
        "loser_name": loser,
        "event_name": event.get("event_name"),
        "bout_date": event.get("event_date"),
        "method": None,
        "source_url": blank_to_none(row.get("fights_url")),
    }


def load_ufcstats_events(location: str | None) -> dict[str, dict[str, str | None]]:
    if not location:
        return {}

    events = {}
    for row in csv.DictReader(open_text(location)):
        url = blank_to_none(row.get("url_link"))
        if not url:
            continue
        events[url] = {
            "event_name": blank_to_none(row.get("event_name")),
            "event_date": blank_to_none(row.get("event_date")),
        }
    return events


def open_text(location: str):
    if location.startswith(("http://", "https://")):
        with urllib.request.urlopen(location, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
        return io.StringIO(text)

    return Path(location).open("r", encoding="utf-8")


def blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


if __name__ == "__main__":
    main()
