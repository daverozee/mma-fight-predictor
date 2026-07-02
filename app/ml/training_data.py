from __future__ import annotations

from collections import defaultdict

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.features import build_matchup_features
from app.ml.fight_history import FighterHistoryState, apply_result, dated_fight_results
from app.ml.fight_history import profile_features_as_of
from app.ml.training import TARGET_COLUMN
from app.models import FighterProfile


def build_training_frame_from_results(db: Session) -> pd.DataFrame:
    profiles = {profile.name: profile for profile in db.scalars(select(FighterProfile)).all()}
    rows: list[dict[str, float | int]] = []
    states: defaultdict[str, FighterHistoryState] = defaultdict(FighterHistoryState)
    for fought_on, fight_id, result in dated_fight_results(db):
        winner = profiles.get(result.winner_name)
        loser = profiles.get(result.loser_name)
        if winner is None or loser is None:
            apply_result(states, result.winner_name, result.loser_name, fought_on, result.method)
            continue

        winner_state = states.setdefault(result.winner_name, FighterHistoryState())
        loser_state = states.setdefault(result.loser_name, FighterHistoryState())
        winner_features = profile_features_as_of(winner, winner_state, fought_on)
        loser_features = profile_features_as_of(loser, loser_state, fought_on)
        metadata = {
            "fight_result_id": fight_id,
            "fight_date": fought_on.isoformat(),
        }
        rows.append(
            {
                **build_matchup_features(winner_features, loser_features),
                TARGET_COLUMN: 1,
                **metadata,
            }
        )
        rows.append(
            {
                **build_matchup_features(loser_features, winner_features),
                TARGET_COLUMN: 0,
                **metadata,
            }
        )
        apply_result(states, result.winner_name, result.loser_name, fought_on, result.method)

    return pd.DataFrame(rows)
