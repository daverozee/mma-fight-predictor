from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.media import media_map_for_names, media_url_for_name
from app.models import FightResult, FighterProfile


def fight_result_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(FightResult)) or 0


def build_defeat_tree(
    db: Session,
    fighter: FighterProfile,
    depth: int = 4,
    max_children: int = 80,
) -> dict[str, object]:
    names_seen: set[str] = set()
    return build_node(db, fighter.name, names_seen, depth, max_children)


def build_node(
    db: Session,
    fighter_name: str,
    names_seen: set[str],
    depth: int,
    max_children: int,
) -> dict[str, object]:
    profile = db.scalar(select(FighterProfile).where(FighterProfile.name == fighter_name))
    media = media_map_for_names(db, [fighter_name]).get(fighter_name)
    node = {
        "id": profile.id if profile else None,
        "name": fighter_name,
        "thumbnail_url": media_url_for_name(media, fighter_name),
        "defeated": [],
    }
    if depth <= 0 or fighter_name in names_seen:
        return node

    next_seen = {*names_seen, fighter_name}
    rows = db.scalars(
        select(FightResult)
        .where(FightResult.winner_name == fighter_name)
        .order_by(FightResult.bout_date.desc(), FightResult.loser_name)
        .limit(max_children)
    ).all()
    node["defeated"] = [
        {
            **build_node(db, row.loser_name, next_seen, depth - 1, max_children),
            "event_name": row.event_name,
            "bout_date": row.bout_date,
            "method": row.method,
            "source": row.source,
        }
        for row in rows
        if row.loser_name not in names_seen
    ]
    return node
