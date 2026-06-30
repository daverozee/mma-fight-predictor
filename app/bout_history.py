from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.matchup_context import parse_bout_date
from app.models import FightResult, FighterProfile


def fighter_bout_history(db: Session, fighter: FighterProfile) -> list[dict[str, object]]:
    rows = db.scalars(
        select(FightResult).where(
            or_(FightResult.winner_name == fighter.name, FightResult.loser_name == fighter.name)
        )
    ).all()
    if not rows:
        return []

    opponent_names = {
        row.loser_name if row.winner_name == fighter.name else row.winner_name
        for row in rows
    }
    opponent_ids = {
        profile.name: profile.id
        for profile in db.scalars(
            select(FighterProfile).where(FighterProfile.name.in_(opponent_names))
        ).all()
    }

    history = []
    for row in rows:
        fought_on = parse_bout_date(row.bout_date)
        won = row.winner_name == fighter.name
        opponent = row.loser_name if won else row.winner_name
        history.append(
            {
                "date": row.bout_date or "Date unavailable",
                "sort_date": fought_on,
                "result": "Win" if won else "Loss",
                "opponent": opponent,
                "opponent_id": opponent_ids.get(opponent),
                "event_name": row.event_name or "Event unavailable",
                "method": row.method or "Method unavailable",
                "source_url": row.source_url,
                "source": row.source,
            }
        )

    fallback_date = parse_bout_date("1900-01-01")
    history.sort(
        key=lambda item: (
            item["sort_date"] is not None,
            item["sort_date"] or fallback_date,
            item["event_name"],
            item["opponent"],
        ),
        reverse=True,
    )
    return history
