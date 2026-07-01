from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.matchup_context import career_arc_context
from app.matchup_context import fighter_career_arc
from app.ml.features import FighterFeatures
from app.ml.predictor import FightPredictor
from app.models import FightResult, FighterProfile


def test_weight_class_mismatch_can_override_smaller_fighter_metrics() -> None:
    featherweight = FighterFeatures(
        name="Elite Featherweight",
        weight_class="Featherweight",
        age=29,
        height_cm=175,
        reach_cm=178,
        wins=22,
        losses=2,
        ko_rate=0.55,
        submission_rate=0.2,
        takedown_accuracy=0.6,
        takedown_defense=0.8,
        strikes_landed_per_min=6.2,
        strikes_absorbed_per_min=2.1,
    )
    heavyweight = FighterFeatures(
        name="Top Heavyweight",
        weight_class="Heavyweight",
        age=32,
        height_cm=193,
        reach_cm=205,
        wins=14,
        losses=5,
        ko_rate=0.35,
        submission_rate=0.1,
        takedown_accuracy=0.3,
        takedown_defense=0.6,
        strikes_landed_per_min=3.1,
        strikes_absorbed_per_min=4.0,
    )

    result = FightPredictor().predict(featherweight, heavyweight)

    assert result["winner"] == "Top Heavyweight"
    assert result["probability_b"] > 0.5
    assert result["insights"][0]["label"] == "Weight class"


def test_actual_weight_handles_unknown_saved_class() -> None:
    lightweight = FighterFeatures(
        name="Conor McGregor",
        weight_class="Lightweight",
        weight_lbs=155,
        age=37,
        height_cm=175,
        reach_cm=188,
        wins=22,
        losses=6,
        ko_rate=0.93,
        submission_rate=0.07,
        takedown_accuracy=0.56,
        takedown_defense=0.66,
        strikes_landed_per_min=5.3,
        strikes_absorbed_per_min=4.7,
    )
    heavyweight = FighterFeatures(
        name="Josh Hokit",
        weight_class="Heavyweight",
        weight_lbs=231,
        age=30,
        height_cm=185,
        reach_cm=185,
        wins=10,
        losses=3,
        ko_rate=0.34,
        submission_rate=0.22,
        takedown_accuracy=0.45,
        takedown_defense=0.69,
        strikes_landed_per_min=4.4,
        strikes_absorbed_per_min=3.4,
    )

    result = FightPredictor().predict(lightweight, heavyweight)

    assert result["winner"] == "Josh Hokit"
    assert result["probability_b"] > 0.5
    assert "76 lb" in result["insights"][0]["detail"]


def test_career_arc_context_favors_active_success_over_old_peak() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        old_peak = profile("Old Peak")
        current_form = profile("Current Form")
        db.add_all(
            [
                old_peak,
                current_form,
                profile("Opponent 1"),
                profile("Opponent 2"),
                profile("Opponent 3"),
                FightResult(
                    winner_name="Old Peak",
                    loser_name="Opponent 1",
                    event_name="Old Event",
                    bout_date="2019-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Old Peak",
                    loser_name="Opponent 2",
                    event_name="Old Event 2",
                    bout_date="2018-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Current Form",
                    loser_name="Opponent 1",
                    event_name="Recent Event",
                    bout_date="2025-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Current Form",
                    loser_name="Opponent 3",
                    event_name="Recent Event 2",
                    bout_date="2024-01-01",
                    source="test",
                ),
            ]
        )
        db.commit()

        context = career_arc_context(db, old_peak, current_form, today=date(2026, 6, 30))

    assert context is not None
    assert context["advantage"] == "Current Form"
    assert context["adjustment_a"] < 0

    result = FightPredictor().predict(
        FighterFeatures(name="Old Peak", weight_class="Lightweight", **even_features()),
        FighterFeatures(name="Current Form", weight_class="Lightweight", **even_features()),
        career_arc=context,
    )

    assert result["winner"] == "Current Form"
    assert result["insights"][0]["label"] == "Career arc"


def test_king_green_career_arc_uses_recent_curated_results() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(profile("King Green"))
        db.add_all(
            [
                FightResult(
                    winner_name="King Green",
                    loser_name="Tony Ferguson",
                    event_name="UFC 291",
                    bout_date="2023-07-29",
                    source="test",
                ),
                FightResult(
                    winner_name="King Green",
                    loser_name="Grant Dawson",
                    event_name="UFC Fight Night 229",
                    bout_date="2023-10-07",
                    source="test",
                ),
                FightResult(
                    winner_name="Jalin Turner",
                    loser_name="King Green",
                    event_name="UFC on ESPN 52",
                    bout_date="2023-12-02",
                    source="test",
                ),
                FightResult(
                    winner_name="King Green",
                    loser_name="Jim Miller",
                    event_name="UFC 300",
                    bout_date="2024-04-13",
                    source="test",
                ),
                FightResult(
                    winner_name="Paddy Pimblett",
                    loser_name="King Green",
                    event_name="UFC 304",
                    bout_date="2024-07-27",
                    source="test",
                ),
                FightResult(
                    winner_name="Mauricio Ruffy",
                    loser_name="King Green",
                    event_name="UFC 313",
                    bout_date="2025-03-08",
                    source="test",
                ),
                FightResult(
                    winner_name="King Green",
                    loser_name="Lance Gibson Jr.",
                    event_name="UFC on ESPN 73",
                    bout_date="2025-12-13",
                    source="test",
                ),
                FightResult(
                    winner_name="King Green",
                    loser_name="Daniel Zellhuber",
                    event_name="UFC Fight Night 268",
                    bout_date="2026-02-28",
                    source="test",
                ),
                FightResult(
                    winner_name="King Green",
                    loser_name="Jeremy Stephens",
                    event_name="UFC 328",
                    bout_date="2026-05-09",
                    source="test",
                ),
            ]
        )
        db.commit()

        arc = fighter_career_arc(db, "King Green", today=date(2026, 7, 1))

    assert arc["recent_record"] == "6-3"
    assert arc["last_fight_years_ago"] == 0.1
    assert arc["sample_size"] == 9


def even_features() -> dict[str, float]:
    return {
        "age": 31,
        "height_cm": 180,
        "reach_cm": 182,
        "wins": 15,
        "losses": 3,
        "ko_rate": 0.4,
        "submission_rate": 0.2,
        "takedown_accuracy": 0.45,
        "takedown_defense": 0.7,
        "strikes_landed_per_min": 4.4,
        "strikes_absorbed_per_min": 3.0,
    }


def profile(name: str) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Lightweight",
        source="test",
        **even_features(),
    )
