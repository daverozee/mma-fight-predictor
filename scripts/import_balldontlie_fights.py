from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import FightResult, FighterProfile  # noqa: E402

API_BASE_URL = "https://api.balldontlie.io/mma/v1"
DEFAULT_SOURCE = "balldontlie-fights-live"


@dataclass(frozen=True)
class ImportSummary:
    fights_seen: int = 0
    imported: int = 0
    skipped: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import completed MMA fight-result edges from BALLDONTLIE."
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="Source label stored on imported fight edges.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Records per API page. BALLDONTLIE allows up to 100.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=250,
        help="Safety cap for full archive pagination.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Optional delay between API pages for low-rate plans.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and normalize fights without writing to the database.",
    )
    args = parser.parse_args()

    api_key = os.getenv("BALLDONTLIE_API_KEY")
    if not api_key:
        raise SystemExit("BALLDONTLIE_API_KEY is required to import live fights.")

    init_db()
    fights = list(
        iter_paginated(
            api_key=api_key,
            path="/fights",
            params={"per_page": min(args.per_page, 100)},
            max_pages=args.max_pages,
            pause_seconds=args.pause_seconds,
        )
    )
    if args.dry_run:
        summary = summarize_fights(fights)
    else:
        with SessionLocal() as db:
            summary = import_fight_edges(db, fights, source=args.source)

    print(f"BALLDONTLIE fights seen: {summary.fights_seen}")
    print(f"Fight result edges imported: {summary.imported}")
    print(f"Fights skipped: {summary.skipped}")


def iter_paginated(
    api_key: str,
    path: str,
    params: dict[str, Any] | None = None,
    max_pages: int = 250,
    pause_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor = None
    for _ in range(max_pages):
        page_params = dict(params or {})
        if cursor is not None:
            page_params["cursor"] = cursor
        payload = request_json(api_key, path, page_params)
        page_records = payload.get("data") or []
        if not isinstance(page_records, list):
            raise ValueError("BALLDONTLIE response data was not a list.")
        records.extend(record for record in page_records if isinstance(record, dict))
        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    return records


def request_json(api_key: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{API_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "User-Agent": "mma-fight-predictor/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        hint = (
            " The /fights endpoint may require a BALLDONTLIE plan with fight access."
            if exc.code == 401
            else ""
        )
        raise RuntimeError(
            f"BALLDONTLIE request failed with HTTP {exc.code}: {message}{hint}"
        ) from exc


def summarize_fights(fights: list[dict[str, Any]]) -> ImportSummary:
    imported = sum(1 for fight in fights if normalize_fight(fight) is not None)
    return ImportSummary(
        fights_seen=len(fights),
        imported=imported,
        skipped=len(fights) - imported,
    )


def import_fight_edges(
    db: Session,
    fights: list[dict[str, Any]],
    source: str = DEFAULT_SOURCE,
) -> ImportSummary:
    profiles = {
        profile.name: profile.id
        for profile in db.scalars(select(FighterProfile)).all()
    }
    imported = 0
    skipped = 0
    for fight in fights:
        edge = normalize_fight(fight)
        if edge is None:
            skipped += 1
            continue
        if existing_result(db, edge):
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
                source=source,
                source_url=edge["source_url"],
            )
        )
        imported += 1
        if imported % 500 == 0:
            db.commit()
    db.commit()
    return ImportSummary(
        fights_seen=len(fights),
        imported=imported,
        skipped=skipped,
    )


def normalize_fight(fight: dict[str, Any]) -> dict[str, str | None] | None:
    status = blank_to_none(fight.get("status"))
    if status is not None and status.lower() != "completed":
        return None

    winner = fighter_name(fight.get("winner"))
    fighter1 = fighter_name(fight.get("fighter1"))
    fighter2 = fighter_name(fight.get("fighter2"))
    if not winner or not fighter1 or not fighter2:
        return None

    if same_fighter(fight.get("winner"), fight.get("fighter1")):
        loser = fighter2
    elif same_fighter(fight.get("winner"), fight.get("fighter2")):
        loser = fighter1
    else:
        return None
    if winner == loser:
        return None

    event = fight.get("event") if isinstance(fight.get("event"), dict) else {}
    method = method_text(fight)
    return {
        "winner_name": winner,
        "loser_name": loser,
        "event_name": blank_to_none(event.get("name")),
        "bout_date": iso_date(event.get("date")),
        "method": method,
        "source_url": fight_url(fight),
    }


def same_fighter(first: Any, second: Any) -> bool:
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    first_id = first.get("id")
    second_id = second.get("id")
    if first_id is not None and second_id is not None:
        return first_id == second_id
    return fighter_name(first) == fighter_name(second)


def fighter_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return blank_to_none(value.get("name"))


def method_text(fight: dict[str, Any]) -> str | None:
    method = blank_to_none(fight.get("result_method"))
    detail = blank_to_none(fight.get("result_method_detail"))
    if method and detail and detail.lower() != method.lower():
        return f"{method} - {detail}"
    return method or detail


def existing_result(db: Session, edge: dict[str, str | None]) -> FightResult | None:
    return db.scalar(
        select(FightResult).where(
            FightResult.winner_name == edge["winner_name"],
            FightResult.loser_name == edge["loser_name"],
            FightResult.event_name == edge["event_name"],
            FightResult.bout_date == edge["bout_date"],
        )
    )


def fight_url(fight: dict[str, Any]) -> str | None:
    fight_id = blank_to_none(fight.get("id"))
    if not fight_id:
        return None
    return f"{API_BASE_URL}/fights/{fight_id}"


def iso_date(value: Any) -> str | None:
    text = blank_to_none(value)
    if not text:
        return None
    return text[:10]


def blank_to_none(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


if __name__ == "__main__":
    main()
