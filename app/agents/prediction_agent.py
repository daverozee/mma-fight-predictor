from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.fighters import features_for_fighter, profile_to_features
from app.matchup_context import career_arc_context
from app.ml.features import FighterFeatures
from app.ml.predictor import FightPredictor, effective_weight_lbs
from app.models import FighterExternalFeature, FighterProfile
from app.sentiment import sample_matchup_sentiment


@dataclass(frozen=True)
class AgentToolRun:
    name: str
    status: str
    summary: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "summary": self.summary}


class PredictionAgent:
    """Structured prediction agent with deterministic tools and an LLM-ready contract."""

    def __init__(self, predictor: FightPredictor | None = None) -> None:
        self.predictor = predictor or FightPredictor()

    def analyze(
        self,
        db: Session,
        profile_a: FighterProfile,
        profile_b: FighterProfile,
        include_sentiment: bool = False,
        sentiment: dict[str, object] | None = None,
    ) -> dict[str, object]:
        settings = get_settings()
        feature_map_a = features_for_fighter(db, profile_a.name)
        feature_map_b = features_for_fighter(db, profile_b.name)
        fighter_a = profile_to_features(profile_a, feature_map_a)
        fighter_b = profile_to_features(profile_b, feature_map_b)
        tool_runs = [
            AgentToolRun(
                "fighter_profile_tool",
                "ready",
                f"Loaded saved profiles and feature maps for {profile_a.name} and {profile_b.name}.",
            )
        ]

        career_arc = career_arc_context(db, profile_a, profile_b)
        tool_runs.append(career_arc_tool_run(career_arc))

        if sentiment is None:
            sentiment = self._sentiment_for_matchup(
                include_sentiment,
                fighter_a.name,
                fighter_b.name,
                settings.sentiment_search_results,
            )
        tool_runs.append(sentiment_tool_run(include_sentiment, sentiment))

        prediction = self.predictor.predict(
            fighter_a,
            fighter_b,
            sentiment=sentiment,
            career_arc=career_arc,
        )
        tool_runs.append(
            AgentToolRun(
                "model_prediction_tool",
                "ready",
                (
                    f"Produced {prediction['comparison_strength'].lower()} profile comparison "
                    f"with {prediction['confidence']:.1%} confidence."
                ),
            )
        )

        data_quality = matchup_data_quality(db, profile_a, profile_b, fighter_a, fighter_b)
        tool_runs.append(
            AgentToolRun(
                "data_quality_tool",
                data_quality["status"],
                data_quality["summary"],
            )
        )

        report = {
            "version": "prediction-agent-v1",
            "mode": "deterministic_orchestrator",
            "status": "ready",
            "winner": prediction["winner"],
            "confidence": prediction["confidence"],
            "tool_runs": [run.as_dict() for run in tool_runs],
            "data_quality": data_quality,
            "model_read": model_read(prediction),
            "wager_readiness": wager_readiness(feature_map_a, feature_map_b),
        }
        return {
            "fighter_a": fighter_a,
            "fighter_b": fighter_b,
            "prediction": prediction,
            "agent": report,
        }

    def _sentiment_for_matchup(
        self,
        include_sentiment: bool,
        fighter_a_name: str,
        fighter_b_name: str,
        results_per_fighter: int,
    ) -> dict[str, object] | None:
        if not include_sentiment:
            return None
        settings = get_settings()
        return sample_matchup_sentiment(
            fighter_a_name,
            fighter_b_name,
            api_key=settings.google_search_api_key,
            engine_id=settings.google_search_engine_id,
            results_per_fighter=results_per_fighter,
        )


def career_arc_tool_run(career_arc: dict[str, object] | None) -> AgentToolRun:
    if not career_arc or not career_arc.get("available"):
        return AgentToolRun(
            "career_arc_tool",
            "limited",
            "Recent-form comparison is not available for both fighters yet.",
        )
    advantage = career_arc.get("advantage")
    if advantage == "Even":
        summary = "Recent-form comparison found no clear career-arc edge."
    else:
        summary = f"Recent-form comparison favors {advantage}."
    return AgentToolRun("career_arc_tool", "ready", summary)


def sentiment_tool_run(
    include_sentiment: bool,
    sentiment: dict[str, object] | None,
) -> AgentToolRun:
    if not include_sentiment:
        return AgentToolRun(
            "sentiment_tool",
            "skipped",
            "Online sentiment sampling was not requested.",
        )
    if sentiment and sentiment.get("available"):
        return AgentToolRun(
            "sentiment_tool",
            "ready",
            f"Sampled {sentiment.get('sample_size', 0)} recent public search results.",
        )
    return AgentToolRun(
        "sentiment_tool",
        "limited",
        "Online sentiment sampling was requested but no live sample was available.",
    )


def matchup_data_quality(
    db: Session,
    profile_a: FighterProfile,
    profile_b: FighterProfile,
    fighter_a: FighterFeatures,
    fighter_b: FighterFeatures,
) -> dict[str, object]:
    fighter_reports = [
        fighter_data_quality(db, profile_a, fighter_a),
        fighter_data_quality(db, profile_b, fighter_b),
    ]
    warnings = [warning for report in fighter_reports for warning in report["warnings"]]
    status = "ready"
    if warnings:
        status = "limited" if len(warnings) >= 3 else "review"
    return {
        "status": status,
        "summary": data_quality_summary(status, warnings),
        "fighters": fighter_reports,
        "warnings": warnings[:8],
    }


def fighter_data_quality(
    db: Session,
    profile: FighterProfile,
    fighter: FighterFeatures,
) -> dict[str, object]:
    feature_rows = db.scalars(
        select(FighterExternalFeature).where(FighterExternalFeature.fighter_name == profile.name)
    ).all()
    sources = sorted({row.source for row in feature_rows})
    feature_names = {row.feature_name for row in feature_rows}
    warnings: list[str] = []
    if profile.source.startswith("provisional"):
        warnings.append(f"{profile.name} uses a provisional profile.")
    if fighter.weight_class == "Unknown" and effective_weight_lbs(fighter) is None:
        warnings.append(f"{profile.name} is missing confirmed weight context.")
    if not sources:
        warnings.append(f"{profile.name} has no external feature sources attached.")
    for expected in ("stance", "camp", "elo_rating", "opponent_strength"):
        if not any(expected in feature_name.lower() for feature_name in feature_names):
            warnings.append(f"{profile.name} is missing {expected.replace('_', ' ')} context.")

    return {
        "name": profile.name,
        "source": profile.source,
        "external_feature_count": len(feature_rows),
        "sources": sources[:8],
        "warnings": warnings[:6],
    }


def data_quality_summary(status: str, warnings: list[str]) -> str:
    if status == "ready":
        return "Both fighters have usable profile data and supporting feature context."
    if status == "review":
        return "The matchup is usable, with a small number of context gaps to review."
    return "The matchup can be analyzed, but several missing data signals may limit confidence."


def model_read(prediction: dict[str, object]) -> dict[str, object]:
    insights = prediction.get("insights") or []
    return {
        "winner": prediction["winner"],
        "confidence": prediction["confidence"],
        "comparison_strength": prediction["comparison_strength"],
        "primary_factors": insights[:3],
        "summary": prediction["summary"],
    }


def wager_readiness(
    feature_map_a: dict[str, str | float],
    feature_map_b: dict[str, str | float],
) -> dict[str, object]:
    odds_a = numeric_feature(feature_map_a, "odds_current")
    odds_b = numeric_feature(feature_map_b, "odds_current")
    checks = [
        "User must confirm every wager before submission.",
        "Sportsbook integration must use an approved API or partner flow.",
        "Age, identity, jurisdiction, account authorization, and responsible gaming limits are required.",
    ]
    if odds_a is None or odds_b is None:
        return {
            "status": "research_only",
            "summary": "No complete current odds pair is available for this matchup.",
            "odds": None,
            "checks": checks,
        }
    return {
        "status": "review_only",
        "summary": "Current odds context is available for research, not automated wagering.",
        "odds": {
            "fighter_a": odds_a,
            "fighter_b": odds_b,
            "fighter_a_implied_probability": implied_probability(odds_a),
            "fighter_b_implied_probability": implied_probability(odds_b),
        },
        "checks": checks,
    }


def numeric_feature(features: dict[str, str | float], key: str) -> float | None:
    value = features.get(key) or features.get(f"supplemental_fighter_features_{key}")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def implied_probability(american_odds: float) -> float:
    if american_odds < 0:
        probability = abs(american_odds) / (abs(american_odds) + 100)
    else:
        probability = 100 / (american_odds + 100)
    return round(probability, 3)


def agent_payload_for_api(analysis: dict[str, Any]) -> dict[str, object]:
    return {
        "prediction": analysis["prediction"],
        "agent": analysis["agent"],
    }
