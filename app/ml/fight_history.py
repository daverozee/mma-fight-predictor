from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matchup_context import parse_bout_date
from app.ml.features import FighterFeatures
from app.models import FightResult, FighterProfile

DEFAULT_ELO = 1500.0
ELO_K_FACTOR = 32.0
RECENT_WINDOW = 5


@dataclass
class FighterHistoryState:
    elo_rating: float = DEFAULT_ELO
    wins: int = 0
    losses: int = 0
    finish_wins: int = 0
    quality_wins: int = 0
    current_streak: int = 0
    last_fight_date: date | None = None
    recent_results: deque[int] = field(default_factory=lambda: deque(maxlen=RECENT_WINDOW))
    opponent_elos: list[float] = field(default_factory=list)

    def feature_payload(self, as_of: date | None = None) -> dict[str, float]:
        days_since_last_fight = 365.0
        if as_of is not None and self.last_fight_date is not None:
            days_since_last_fight = float(max((as_of - self.last_fight_date).days, 0))
        return {
            "elo_rating": round(self.elo_rating, 3),
            "opponent_elo_avg": round(
                sum(self.opponent_elos) / len(self.opponent_elos)
                if self.opponent_elos
                else DEFAULT_ELO,
                3,
            ),
            "recent_win_rate": round(
                sum(self.recent_results) / len(self.recent_results)
                if self.recent_results
                else 0.5,
                3,
            ),
            "current_streak": float(self.current_streak),
            "days_since_last_fight": round(days_since_last_fight, 3),
            "finish_rate": round(self.finish_wins / self.wins if self.wins else 0.0, 3),
            "quality_win_rate": round(self.quality_wins / self.wins if self.wins else 0.0, 3),
        }


def historical_features_for_fighter(
    db: Session,
    fighter_name: str,
    as_of: date | None = None,
) -> dict[str, float]:
    states = states_before_date(db, as_of)
    return states[fighter_name].feature_payload(as_of)


def profile_features_as_of(
    profile: FighterProfile,
    state: FighterHistoryState,
    as_of: date | None,
) -> FighterFeatures:
    wins = float(state.wins)
    losses = float(state.losses)
    return FighterFeatures(
        name=profile.name,
        weight_class=profile.weight_class,
        age=profile.age,
        height_cm=profile.height_cm,
        reach_cm=profile.reach_cm,
        wins=wins,
        losses=losses,
        ko_rate=profile.ko_rate,
        submission_rate=profile.submission_rate,
        takedown_accuracy=profile.takedown_accuracy,
        takedown_defense=profile.takedown_defense,
        strikes_landed_per_min=profile.strikes_landed_per_min,
        strikes_absorbed_per_min=profile.strikes_absorbed_per_min,
        **state.feature_payload(as_of),
    )


def states_before_date(
    db: Session,
    as_of: date | None,
) -> defaultdict[str, FighterHistoryState]:
    states: defaultdict[str, FighterHistoryState] = defaultdict(FighterHistoryState)
    rows = dated_fight_results(db)
    for fought_on, _, row in rows:
        if as_of is not None and fought_on >= as_of:
            continue
        apply_result(states, row.winner_name, row.loser_name, fought_on, row.method)
    return states


def dated_fight_results(db: Session) -> list[tuple[date, int, FightResult]]:
    rows = db.scalars(select(FightResult)).all()
    dated_rows = []
    for row in rows:
        fought_on = parse_bout_date(row.bout_date)
        if fought_on is None:
            continue
        dated_rows.append((fought_on, row.id or 0, row))
    return sorted(dated_rows, key=lambda item: (item[0], item[1]))


def fighter_results_before(
    db: Session,
    fighter_name: str,
    before: date,
) -> list[FightResult]:
    return [
        row
        for fought_on, _, row in dated_fight_results(db)
        if fought_on < before and (row.winner_name == fighter_name or row.loser_name == fighter_name)
    ]


def apply_result(
    states: defaultdict[str, FighterHistoryState],
    winner_name: str,
    loser_name: str,
    fought_on: date,
    method: str | None,
) -> None:
    winner = states[winner_name]
    loser = states[loser_name]
    winner_pre_elo = winner.elo_rating
    loser_pre_elo = loser.elo_rating

    winner_expected = expected_score(winner_pre_elo, loser_pre_elo)
    loser_expected = 1.0 - winner_expected
    winner.elo_rating = winner_pre_elo + ELO_K_FACTOR * (1.0 - winner_expected)
    loser.elo_rating = loser_pre_elo + ELO_K_FACTOR * (0.0 - loser_expected)

    winner.wins += 1
    loser.losses += 1
    if is_finish(method):
        winner.finish_wins += 1
    if loser_pre_elo >= DEFAULT_ELO:
        winner.quality_wins += 1

    winner.current_streak = winner.current_streak + 1 if winner.current_streak >= 0 else 1
    loser.current_streak = loser.current_streak - 1 if loser.current_streak <= 0 else -1
    winner.recent_results.append(1)
    loser.recent_results.append(0)
    winner.opponent_elos.append(loser_pre_elo)
    loser.opponent_elos.append(winner_pre_elo)
    winner.last_fight_date = fought_on
    loser.last_fight_date = fought_on


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def is_finish(method: str | None) -> bool:
    normalized = (method or "").lower()
    if not normalized:
        return False
    non_finishes = ("decision", "draw", "no contest", "overturned")
    return not any(term in normalized for term in non_finishes)
