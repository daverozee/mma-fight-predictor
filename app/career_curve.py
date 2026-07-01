from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.matchup_context import parse_bout_date
from app.models import FightResult, FighterProfile

VIEWBOX_WIDTH = 320
VIEWBOX_HEIGHT = 170
CHART_LEFT = 36
CHART_RIGHT = 12
CHART_TOP = 14
CHART_BOTTOM = 34
CHART_WIDTH = VIEWBOX_WIDTH - CHART_LEFT - CHART_RIGHT
CHART_HEIGHT = VIEWBOX_HEIGHT - CHART_TOP - CHART_BOTTOM


def fighter_career_curve(db: Session, fighter: FighterProfile) -> dict[str, object]:
    rows = db.scalars(
        select(FightResult).where(
            or_(
                FightResult.winner_name == fighter.name,
                FightResult.loser_name == fighter.name,
            )
        )
    ).all()
    dated_results = []
    for row in rows:
        fought_on = parse_bout_date(row.bout_date)
        if fought_on is None:
            continue
        dated_results.append((fought_on, row.id or 0, row.winner_name == fighter.name, row))

    dated_results.sort(key=lambda result: (result[0], result[1]))
    if not dated_results:
        return {
            "available": False,
            "total_bouts": 0,
            "total_victories": 0,
            "total_losses": 0,
            "viewbox": f"0 0 {VIEWBOX_WIDTH} {VIEWBOX_HEIGHT}",
        }

    victories = 0
    losses = 0
    raw_points = []
    for fought_on, _row_id, won, row in dated_results:
        if won:
            victories += 1
        else:
            losses += 1
        raw_points.append(
            {
                "date": fought_on,
                "date_label": fought_on.strftime("%b %Y"),
                "victories": victories,
                "losses": losses,
                "outcome": "Win" if won else "Loss",
                "opponent": row.loser_name if won else row.winner_name,
            }
        )

    y_max = max(1, victories, losses)
    first_date = raw_points[0]["date"]
    last_date = raw_points[-1]["date"]
    span_days = (last_date - first_date).days
    bottom_y = CHART_TOP + CHART_HEIGHT
    points = []
    for index, point in enumerate(raw_points):
        if span_days > 0:
            x_ratio = (point["date"] - first_date).days / span_days
        else:
            x_ratio = index / max(len(raw_points) - 1, 1)
        victory_y_ratio = point["victories"] / y_max
        loss_y_ratio = point["losses"] / y_max
        x = round(CHART_LEFT + x_ratio * CHART_WIDTH, 1)
        victory_y = round(bottom_y - victory_y_ratio * CHART_HEIGHT, 1)
        loss_y = round(bottom_y - loss_y_ratio * CHART_HEIGHT, 1)
        points.append(
            {
                "x": x,
                "victory_y": victory_y,
                "loss_y": loss_y,
                "date_label": point["date_label"],
                "victories": point["victories"],
                "losses": point["losses"],
                "outcome": point["outcome"],
                "opponent": point["opponent"],
            }
        )

    win_polyline = " ".join(
        [f"{CHART_LEFT},{bottom_y}", *[f"{p['x']},{p['victory_y']}" for p in points]]
    )
    loss_polyline = " ".join(
        [f"{CHART_LEFT},{bottom_y}", *[f"{p['x']},{p['loss_y']}" for p in points]]
    )
    return {
        "available": True,
        "viewbox": f"0 0 {VIEWBOX_WIDTH} {VIEWBOX_HEIGHT}",
        "axis": {
            "x1": CHART_LEFT,
            "x2": VIEWBOX_WIDTH - CHART_RIGHT,
            "y1": CHART_TOP,
            "y2": bottom_y,
        },
        "first_label": first_date.strftime("%Y"),
        "last_label": last_date.strftime("%Y"),
        "total_bouts": len(raw_points),
        "total_victories": victories,
        "total_losses": losses,
        "y_max": y_max,
        "win_polyline": win_polyline,
        "loss_polyline": loss_polyline,
        "points": points,
    }
