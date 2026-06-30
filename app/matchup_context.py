from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import FightResult, FighterProfile


def career_arc_context(
    db: Session,
    fighter_a: FighterProfile,
    fighter_b: FighterProfile,
    today: date | None = None,
) -> dict[str, object] | None:
    today = today or datetime.now(timezone.utc).date()
    arc_a = fighter_career_arc(db, fighter_a.name, today)
    arc_b = fighter_career_arc(db, fighter_b.name, today)
    if not arc_a["available"] or not arc_b["available"]:
        return None

    score_diff = float(arc_a["score"]) - float(arc_b["score"])
    if abs(score_diff) < 0.18:
        adjustment = 0.0
        advantage = "Even"
    else:
        adjustment = max(-0.08, min(0.08, score_diff * 0.08))
        advantage = fighter_a.name if adjustment > 0 else fighter_b.name

    return {
        "available": True,
        "adjustment_a": round(adjustment, 3),
        "advantage": advantage,
        "fighter_a": arc_a,
        "fighter_b": arc_b,
    }


def fighter_career_arc(db: Session, fighter_name: str, today: date) -> dict[str, object]:
    rows = db.scalars(
        select(FightResult)
        .where(or_(FightResult.winner_name == fighter_name, FightResult.loser_name == fighter_name))
        .order_by(FightResult.bout_date.desc())
    ).all()
    dated_results = []
    for row in rows:
        fought_on = parse_bout_date(row.bout_date)
        if fought_on is None:
            continue
        years_ago = max((today - fought_on).days / 365.25, 0)
        outcome = 1 if row.winner_name == fighter_name else -1
        dated_results.append((years_ago, outcome))

    if not dated_results:
        return {
            "available": False,
            "name": fighter_name,
            "score": 0.0,
            "recent_record": "0-0",
            "sample_size": 0,
        }

    weighted_total = 0.0
    total_weight = 0.0
    recent_wins = 0
    recent_losses = 0
    for years_ago, outcome in dated_results:
        weight = recency_weight(years_ago)
        weighted_total += outcome * weight
        total_weight += weight
        if years_ago <= 3:
            if outcome > 0:
                recent_wins += 1
            else:
                recent_losses += 1

    last_fight_years_ago = min(years_ago for years_ago, _ in dated_results)
    inactivity_penalty = max(0.0, min(0.35, (last_fight_years_ago - 3) * 0.08))
    score = (weighted_total / total_weight) - inactivity_penalty if total_weight else 0.0
    score = max(-1.0, min(1.0, score))
    return {
        "available": True,
        "name": fighter_name,
        "score": round(score, 3),
        "recent_record": f"{recent_wins}-{recent_losses}",
        "last_fight_years_ago": round(last_fight_years_ago, 1),
        "sample_size": len(dated_results),
    }


def recency_weight(years_ago: float) -> float:
    if years_ago <= 1.5:
        return 1.0
    if years_ago <= 3:
        return 0.75
    if years_ago <= 5:
        return 0.45
    if years_ago <= 7:
        return 0.22
    return 0.08


def parse_bout_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = value.strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None
