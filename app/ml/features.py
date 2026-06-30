from pydantic import BaseModel, Field


class FighterFeatures(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    weight_class: str = Field(default="Unknown", max_length=80)
    weight_lbs: float | None = Field(default=None, ge=90, le=300)
    age: float = Field(ge=18, le=60)
    height_cm: float = Field(ge=140, le=230)
    reach_cm: float = Field(ge=140, le=230)
    wins: float = Field(ge=0, le=100)
    losses: float = Field(ge=0, le=100)
    ko_rate: float = Field(ge=0, le=1)
    submission_rate: float = Field(ge=0, le=1)
    takedown_accuracy: float = Field(ge=0, le=1)
    takedown_defense: float = Field(ge=0, le=1)
    strikes_landed_per_min: float = Field(ge=0, le=15)
    strikes_absorbed_per_min: float = Field(ge=0, le=15)


FEATURE_COLUMNS = [
    "age_diff",
    "height_diff",
    "reach_diff",
    "experience_diff",
    "win_rate_diff",
    "ko_rate_diff",
    "submission_rate_diff",
    "takedown_accuracy_diff",
    "takedown_defense_diff",
    "striking_diff",
    "defense_diff",
]


def build_matchup_features(fighter_a: FighterFeatures, fighter_b: FighterFeatures) -> dict[str, float]:
    a_total = max(fighter_a.wins + fighter_a.losses, 1)
    b_total = max(fighter_b.wins + fighter_b.losses, 1)
    return {
        "age_diff": fighter_a.age - fighter_b.age,
        "height_diff": fighter_a.height_cm - fighter_b.height_cm,
        "reach_diff": fighter_a.reach_cm - fighter_b.reach_cm,
        "experience_diff": (fighter_a.wins + fighter_a.losses) - (fighter_b.wins + fighter_b.losses),
        "win_rate_diff": (fighter_a.wins / a_total) - (fighter_b.wins / b_total),
        "ko_rate_diff": fighter_a.ko_rate - fighter_b.ko_rate,
        "submission_rate_diff": fighter_a.submission_rate - fighter_b.submission_rate,
        "takedown_accuracy_diff": fighter_a.takedown_accuracy - fighter_b.takedown_accuracy,
        "takedown_defense_diff": fighter_a.takedown_defense - fighter_b.takedown_defense,
        "striking_diff": fighter_a.strikes_landed_per_min - fighter_b.strikes_landed_per_min,
        "defense_diff": fighter_b.strikes_absorbed_per_min - fighter_a.strikes_absorbed_per_min,
    }
