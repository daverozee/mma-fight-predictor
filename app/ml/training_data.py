from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fighters import profile_to_features
from app.ml.features import build_matchup_features
from app.ml.training import TARGET_COLUMN
from app.models import FightResult, FighterProfile


def build_training_frame_from_results(db: Session) -> pd.DataFrame:
    profiles = {profile.name: profile for profile in db.scalars(select(FighterProfile)).all()}
    rows: list[dict[str, float | int]] = []
    results = db.scalars(select(FightResult).order_by(FightResult.bout_date)).all()
    for result in results:
        winner = profiles.get(result.winner_name)
        loser = profiles.get(result.loser_name)
        if winner is None or loser is None:
            continue

        winner_features = profile_to_features(winner)
        loser_features = profile_to_features(loser)
        rows.append(
            {
                **build_matchup_features(winner_features, loser_features),
                TARGET_COLUMN: 1,
            }
        )
        rows.append(
            {
                **build_matchup_features(loser_features, winner_features),
                TARGET_COLUMN: 0,
            }
        )

    return pd.DataFrame(rows)
