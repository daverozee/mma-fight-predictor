from pathlib import Path
from collections.abc import Callable

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from app.config import get_settings
from app.ml.features import FEATURE_COLUMNS, FighterFeatures, build_matchup_features
from app.ml.training import train_model
from app.weight_classes import canonical_weight_class, weight_class_limit_lbs


EPSILON = 1e-9


class FightPredictor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model_path = Path(self.settings.model_path)
        self.data_path = Path(__file__).resolve().parents[1] / "data" / "sample_fights.csv"
        self._model: Pipeline | None = None

    def model(self) -> Pipeline:
        if self._model is None:
            if not self.model_path.exists():
                train_model(self.data_path, self.model_path)
            self._model = joblib.load(self.model_path)
        return self._model

    def predict(
        self,
        fighter_a: FighterFeatures,
        fighter_b: FighterFeatures,
        sentiment: dict[str, object] | None = None,
        career_arc: dict[str, object] | None = None,
    ) -> dict[str, object]:
        features = build_matchup_features(fighter_a, fighter_b)
        insights = matchup_insights(features, fighter_a, fighter_b)
        comparison_strength = comparison_strength_label(features)
        sentiment_available = bool(sentiment and sentiment.get("available"))
        weight_adjustment = weight_class_adjustment(fighter_a, fighter_b)
        career_adjustment = career_arc_adjustment(career_arc)
        context_insights = weight_class_insights(fighter_a, fighter_b) + career_arc_insights(
            career_arc
        )
        context_available = bool(context_insights)
        if not insights and not sentiment_available and not context_available:
            return {
                "winner": "No clear edge",
                "probability_a": 0.5,
                "probability_b": 0.5,
                "confidence": 0.5,
                "features": features,
                "insights": [],
                "sentiment": sentiment,
                "career_arc": career_arc,
                "comparison_strength": comparison_strength,
                "profile_rows": profile_comparison_rows(fighter_a, fighter_b),
                "summary": (
                    "The saved profiles for these fighters currently contain the same "
                    "measurable values, so there is not enough separation to favor either side."
                ),
            }

        if insights:
            frame = pd.DataFrame([{column: features[column] for column in FEATURE_COLUMNS}])
            probability_a = float(self.model().predict_proba(frame)[0][1])
        else:
            probability_a = 0.5
        probability_a = apply_probability_adjustment(
            probability_a,
            weight_adjustment + career_adjustment,
        )
        probability_a = apply_sentiment_adjustment(probability_a, sentiment)
        winner = fighter_a.name if probability_a >= 0.5 else fighter_b.name
        confidence = probability_a if probability_a >= 0.5 else 1 - probability_a
        display_insights = (
            context_insights + insights + sentiment_insights(sentiment, fighter_a.name, fighter_b.name)
        )
        return {
            "winner": winner,
            "probability_a": round(probability_a, 3),
            "probability_b": round(1 - probability_a, 3),
            "confidence": round(confidence, 3),
            "features": features,
            "insights": display_insights,
            "sentiment": sentiment,
            "career_arc": career_arc,
            "comparison_strength": comparison_strength,
            "profile_rows": profile_comparison_rows(fighter_a, fighter_b),
            "summary": (
                f"{winner} is favored by the current profile comparison. The strongest "
                "measurable advantages are listed below."
            ),
        }


def comparison_strength_label(features: dict[str, float]) -> str:
    meaningful_count = sum(1 for value in features.values() if abs(value) > EPSILON)
    if meaningful_count == 0:
        return "Limited"
    if meaningful_count < 4:
        return "Developing"
    return "Standard"


def apply_probability_adjustment(probability_a: float, adjustment: float) -> float:
    return max(0.01, min(0.99, probability_a + adjustment))


def weight_class_adjustment(fighter_a: FighterFeatures, fighter_b: FighterFeatures) -> float:
    limit_a = weight_class_limit_lbs(fighter_a.weight_class)
    limit_b = weight_class_limit_lbs(fighter_b.weight_class)
    if limit_a is None or limit_b is None or limit_a == limit_b:
        return 0.0
    difference = limit_a - limit_b
    adjustment = max(-0.55, min(0.55, (difference / 100) * 0.5))
    return round(adjustment, 3)


def career_arc_adjustment(career_arc: dict[str, object] | None) -> float:
    if not career_arc or not career_arc.get("available"):
        return 0.0
    return float(career_arc.get("adjustment_a", 0.0))


def weight_class_insights(
    fighter_a: FighterFeatures,
    fighter_b: FighterFeatures,
) -> list[dict[str, str]]:
    adjustment = weight_class_adjustment(fighter_a, fighter_b)
    if abs(adjustment) <= EPSILON:
        return []
    limit_a = weight_class_limit_lbs(fighter_a.weight_class)
    limit_b = weight_class_limit_lbs(fighter_b.weight_class)
    class_a = canonical_weight_class(fighter_a.weight_class) or fighter_a.weight_class
    class_b = canonical_weight_class(fighter_b.weight_class) or fighter_b.weight_class
    advantage = fighter_a.name if adjustment > 0 else fighter_b.name
    heavier = class_a if adjustment > 0 else class_b
    lighter = class_b if adjustment > 0 else class_a
    gap = abs((limit_a or 0) - (limit_b or 0))
    return [
        {
            "label": "Weight class",
            "advantage": advantage,
            "detail": f"{heavier} is {gap:.0f} lb above {lighter}",
        }
    ]


def career_arc_insights(career_arc: dict[str, object] | None) -> list[dict[str, str]]:
    if (
        not career_arc
        or not career_arc.get("available")
        or career_arc.get("advantage") == "Even"
    ):
        return []
    advantage = str(career_arc["advantage"])
    fighter = (
        career_arc["fighter_a"]
        if career_arc["fighter_a"]["name"] == advantage
        else career_arc["fighter_b"]
    )
    return [
        {
            "label": "Career arc",
            "advantage": advantage,
            "detail": (
                f"{fighter['recent_record']} in the last three years, "
                f"last fought {fighter['last_fight_years_ago']} years ago"
            ),
        }
    ]


def apply_sentiment_adjustment(
    probability_a: float,
    sentiment: dict[str, object] | None,
) -> float:
    if not sentiment or not sentiment.get("available"):
        return probability_a
    fighter_a = sentiment.get("fighter_a") or {}
    fighter_b = sentiment.get("fighter_b") or {}
    score_a = float(fighter_a.get("score", 0))
    score_b = float(fighter_b.get("score", 0))
    adjustment = max(-0.06, min(0.06, (score_a - score_b) * 0.04))
    sentiment["adjustment"] = round(adjustment, 3)
    return max(0.01, min(0.99, probability_a + adjustment))


def sentiment_insights(
    sentiment: dict[str, object] | None,
    fighter_a_name: str,
    fighter_b_name: str,
) -> list[dict[str, str]]:
    if not sentiment or not sentiment.get("available"):
        return []
    fighter_a = sentiment.get("fighter_a") or {}
    fighter_b = sentiment.get("fighter_b") or {}
    score_a = float(fighter_a.get("score", 0))
    score_b = float(fighter_b.get("score", 0))
    if abs(score_a - score_b) < 0.08:
        return []
    advantage = fighter_a_name if score_a > score_b else fighter_b_name
    sample_size = int(sentiment.get("sample_size", 0))
    return [
        {
            "label": "Online pulse",
            "advantage": advantage,
            "detail": f"More positive recent search sample across {sample_size} results",
        }
    ]


def matchup_insights(
    features: dict[str, float],
    fighter_a: FighterFeatures,
    fighter_b: FighterFeatures,
) -> list[dict[str, str]]:
    insight_builders: dict[str, tuple[float, Callable[[float], dict[str, str] | None]]] = {
        "age_diff": (5, lambda value: age_insight(value, fighter_a.name, fighter_b.name)),
        "height_diff": (
            10,
            lambda value: higher_is_better(
                value,
                fighter_a.name,
                fighter_b.name,
                "Height",
                "taller",
                "cm",
            ),
        ),
        "reach_diff": (
            10,
            lambda value: higher_is_better(
                value,
                fighter_a.name,
                fighter_b.name,
                "Reach",
                "longer reach",
                "cm",
            ),
        ),
        "experience_diff": (
            10,
            lambda value: higher_is_better(
                value,
                fighter_a.name,
                fighter_b.name,
                "Experience",
                "more recorded bouts",
                "bouts",
            ),
        ),
        "win_rate_diff": (
            0.15,
            lambda value: rate_insight(value, fighter_a.name, fighter_b.name, "Win rate"),
        ),
        "ko_rate_diff": (
            0.15,
            lambda value: rate_insight(value, fighter_a.name, fighter_b.name, "KO rate"),
        ),
        "submission_rate_diff": (
            0.15,
            lambda value: rate_insight(value, fighter_a.name, fighter_b.name, "Submission rate"),
        ),
        "takedown_accuracy_diff": (
            0.15,
            lambda value: rate_insight(
                value, fighter_a.name, fighter_b.name, "Takedown accuracy"
            ),
        ),
        "takedown_defense_diff": (
            0.15,
            lambda value: rate_insight(value, fighter_a.name, fighter_b.name, "Takedown defense"),
        ),
        "striking_diff": (
            1,
            lambda value: higher_is_better(
                value,
                fighter_a.name,
                fighter_b.name,
                "Striking pace",
                "more landed strikes per minute",
                "SLpM",
            ),
        ),
        "defense_diff": (
            1,
            lambda value: higher_is_better(
                value,
                fighter_a.name,
                fighter_b.name,
                "Strike absorption",
                "fewer absorbed strikes per minute",
                "SApM",
            ),
        ),
    }
    ranked = sorted(
        (
            (abs(value) / scale, builder(value))
            for key, value in features.items()
            if abs(value) > EPSILON
            for scale, builder in [insight_builders[key]]
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    return [insight for _, insight in ranked[:5] if insight is not None]


def age_insight(value: float, fighter_a_name: str, fighter_b_name: str) -> dict[str, str] | None:
    if abs(value) <= EPSILON:
        return None
    advantage = fighter_a_name if value < 0 else fighter_b_name
    return {
        "label": "Age",
        "advantage": advantage,
        "detail": f"{abs(value):.1f} years younger",
    }


def higher_is_better(
    value: float,
    fighter_a_name: str,
    fighter_b_name: str,
    label: str,
    phrase: str,
    unit: str,
) -> dict[str, str] | None:
    if abs(value) <= EPSILON:
        return None
    advantage = fighter_a_name if value > 0 else fighter_b_name
    amount = f"{abs(value):.1f}" if unit in {"cm", "bouts"} else f"{abs(value):.2f}"
    return {
        "label": label,
        "advantage": advantage,
        "detail": f"{amount} {unit} {phrase}",
    }


def rate_insight(
    value: float,
    fighter_a_name: str,
    fighter_b_name: str,
    label: str,
) -> dict[str, str] | None:
    if abs(value) <= EPSILON:
        return None
    advantage = fighter_a_name if value > 0 else fighter_b_name
    return {
        "label": label,
        "advantage": advantage,
        "detail": f"{abs(value) * 100:.1f} percentage points higher",
    }


def profile_comparison_rows(
    fighter_a: FighterFeatures,
    fighter_b: FighterFeatures,
) -> list[dict[str, str]]:
    a_total = max(fighter_a.wins + fighter_a.losses, 1)
    b_total = max(fighter_b.wins + fighter_b.losses, 1)
    rows = [
        {
            "label": "Weight class",
            "a": fighter_a.weight_class,
            "b": fighter_b.weight_class,
            "edge": weight_class_edge(fighter_a, fighter_b),
        },
        comparison_row("Age", fighter_a.age, fighter_b.age, fighter_a.name, fighter_b.name, False),
        comparison_row(
            "Height",
            fighter_a.height_cm,
            fighter_b.height_cm,
            fighter_a.name,
            fighter_b.name,
            True,
            " cm",
        ),
        comparison_row(
            "Reach",
            fighter_a.reach_cm,
            fighter_b.reach_cm,
            fighter_a.name,
            fighter_b.name,
            True,
            " cm",
        ),
        {
            "label": "Record",
            "a": f"{fighter_a.wins:.0f}-{fighter_a.losses:.0f}",
            "b": f"{fighter_b.wins:.0f}-{fighter_b.losses:.0f}",
            "edge": edge_label(
                fighter_a.wins / a_total,
                fighter_b.wins / b_total,
                fighter_a.name,
                fighter_b.name,
                True,
            ),
        },
        percentage_row(
            "Win rate",
            fighter_a.wins / a_total,
            fighter_b.wins / b_total,
            fighter_a.name,
            fighter_b.name,
        ),
        percentage_row("KO rate", fighter_a.ko_rate, fighter_b.ko_rate, fighter_a.name, fighter_b.name),
        percentage_row(
            "Submission rate",
            fighter_a.submission_rate,
            fighter_b.submission_rate,
            fighter_a.name,
            fighter_b.name,
        ),
        percentage_row(
            "Takedown accuracy",
            fighter_a.takedown_accuracy,
            fighter_b.takedown_accuracy,
            fighter_a.name,
            fighter_b.name,
        ),
        percentage_row(
            "Takedown defense",
            fighter_a.takedown_defense,
            fighter_b.takedown_defense,
            fighter_a.name,
            fighter_b.name,
        ),
        comparison_row(
            "Strikes landed/min",
            fighter_a.strikes_landed_per_min,
            fighter_b.strikes_landed_per_min,
            fighter_a.name,
            fighter_b.name,
            True,
        ),
        comparison_row(
            "Strikes absorbed/min",
            fighter_a.strikes_absorbed_per_min,
            fighter_b.strikes_absorbed_per_min,
            fighter_a.name,
            fighter_b.name,
            False,
        ),
    ]
    return rows


def weight_class_edge(fighter_a: FighterFeatures, fighter_b: FighterFeatures) -> str:
    adjustment = weight_class_adjustment(fighter_a, fighter_b)
    if abs(adjustment) <= EPSILON:
        return "Even"
    return fighter_a.name if adjustment > 0 else fighter_b.name


def percentage_row(
    label: str,
    value_a: float,
    value_b: float,
    fighter_a_name: str,
    fighter_b_name: str,
) -> dict[str, str]:
    return {
        "label": label,
        "a": f"{value_a * 100:.1f}%",
        "b": f"{value_b * 100:.1f}%",
        "edge": edge_label(value_a, value_b, fighter_a_name, fighter_b_name, True),
    }


def comparison_row(
    label: str,
    value_a: float,
    value_b: float,
    fighter_a_name: str,
    fighter_b_name: str,
    higher_is_edge: bool,
    suffix: str = "",
) -> dict[str, str]:
    return {
        "label": label,
        "a": f"{value_a:.1f}{suffix}",
        "b": f"{value_b:.1f}{suffix}",
        "edge": edge_label(value_a, value_b, fighter_a_name, fighter_b_name, higher_is_edge),
    }


def edge_label(
    value_a: float,
    value_b: float,
    fighter_a_name: str,
    fighter_b_name: str,
    higher_is_edge: bool,
) -> str:
    if abs(value_a - value_b) <= EPSILON:
        return "Even"
    if higher_is_edge:
        return fighter_a_name if value_a > value_b else fighter_b_name
    return fighter_a_name if value_a < value_b else fighter_b_name
