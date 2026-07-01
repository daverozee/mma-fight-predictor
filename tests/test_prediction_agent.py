from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.prediction_agent import PredictionAgent, implied_probability
from app.database import Base
from app.models import FighterExternalFeature, FighterProfile


def test_prediction_agent_returns_structured_report() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        fighter_a = profile("Agent A", wins=15, losses=3)
        fighter_b = profile("Agent B", wins=9, losses=5)
        db.add_all([fighter_a, fighter_b])
        db.add_all(
            [
                feature("Agent A", "odds_current", -145),
                feature("Agent B", "odds_current", 125),
                feature("Agent A", "camp", "Example MMA"),
                feature("Agent B", "camp", "Example Fight Team"),
            ]
        )
        db.commit()

        analysis = PredictionAgent().analyze(db, fighter_a, fighter_b)

    assert analysis["prediction"]["winner"]
    assert analysis["agent"]["version"] == "prediction-agent-v1"
    assert analysis["agent"]["mode"] == "deterministic_orchestrator"
    assert analysis["agent"]["tool_runs"]
    assert analysis["agent"]["data_quality"]["fighters"][0]["name"] == "Agent A"
    assert analysis["agent"]["wager_readiness"]["status"] == "review_only"
    assert analysis["agent"]["wager_readiness"]["odds"]["fighter_a"] == -145


def test_implied_probability_for_american_odds() -> None:
    assert implied_probability(-150) == 0.6
    assert implied_probability(200) == 0.333


def profile(name: str, wins: int, losses: int) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Lightweight",
        age=30,
        height_cm=180,
        reach_cm=184,
        wins=wins,
        losses=losses,
        ko_rate=0.3,
        submission_rate=0.2,
        takedown_accuracy=0.4,
        takedown_defense=0.7,
        strikes_landed_per_min=4.2,
        strikes_absorbed_per_min=3.1,
        source="test",
    )


def feature(name: str, feature_name: str, value: str | float) -> FighterExternalFeature:
    return FighterExternalFeature(
        fighter_name=name,
        feature_name=feature_name,
        numeric_value=value if isinstance(value, int | float) else None,
        text_value=value if isinstance(value, str) else None,
        source="test",
    )
