from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.card_analyzer import analyze_upcoming_cards
from app.database import Base
from app.models import FighterExternalFeature, FighterProfile


def test_card_analyzer_groups_upcoming_odds_and_predicts() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add_all([profile("Fighter A"), profile("Fighter B")])
        db.flush()
        add_odds_event(
            db,
            home="Fighter A",
            away="Fighter B",
            commence_time="2026-07-12T02:30:00Z",
            bookmakers=(
                "[{'title': 'Book One', 'markets': [{'key': 'h2h', 'outcomes': "
                "[{'name': 'Fighter A', 'price': -150}, {'name': 'Fighter B', 'price': 130}]}]}, "
                "{'title': 'Book Two', 'markets': [{'key': 'h2h', 'outcomes': "
                "[{'name': 'Fighter A', 'price': -170}, {'name': 'Fighter B', 'price': 140}]}]}]"
            ),
        )
        db.commit()

        analysis = analyze_upcoming_cards(
            db,
            FakePredictionAgent(),
            now=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

    assert analysis["summary"] == {
        "cards": 1,
        "fights": 1,
        "predictions": 1,
        "missing_profile_fights": 0,
    }
    fight = analysis["cards"][0]["fights"][0]
    assert fight["prediction_status"] == "ready"
    assert fight["prediction"]["winner"] == "Fighter A"
    assert fight["odds"]["fighter_a"] == -160
    assert fight["odds"]["fighter_b"] == 135
    assert fight["odds"]["bookmaker_count"] == 2


def test_card_analyzer_marks_missing_profiles() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(profile("Fighter A"))
        add_odds_event(
            db,
            home="Fighter A",
            away="Unmatched Fighter",
            commence_time="2026-07-12T02:30:00Z",
            bookmakers="[]",
        )
        db.commit()

        analysis = analyze_upcoming_cards(
            db,
            FakePredictionAgent(),
            now=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

    fight = analysis["cards"][0]["fights"][0]
    assert fight["prediction_status"] == "missing_profile"
    assert fight["missing_profiles"] == ["Unmatched Fighter"]
    assert analysis["summary"]["missing_profile_fights"] == 1


class FakePredictionAgent:
    def analyze(self, db, profile_a, profile_b, include_sentiment=False):
        return {
            "prediction": {
                "winner": profile_a.name,
                "confidence": 0.61,
                "insights": [
                    {
                        "label": "Win rate",
                        "advantage": profile_a.name,
                        "detail": "Sample edge",
                    }
                ],
            },
            "agent": {
                "data_quality": {"status": "ready"},
                "wager_readiness": {"status": "research_only"},
            },
        }


def add_odds_event(
    db,
    home: str,
    away: str,
    commence_time: str,
    bookmakers: str,
) -> None:
    source = "the-odds-api-mma-current"
    prefix = "the_odds_api_mma_current_"
    for feature_name, value in {
        "id": f"{home}-{away}",
        "sport_key": "mma_mixed_martial_arts",
        "sport_title": "MMA",
        "commence_time": commence_time,
        "away_team": away,
        "bookmakers": bookmakers,
    }.items():
        db.add(
            FighterExternalFeature(
                fighter_name=home,
                feature_name=f"{prefix}{feature_name}",
                text_value=value,
                source=source,
            )
        )


def profile(name: str) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Lightweight",
        age=30,
        height_cm=180,
        reach_cm=184,
        wins=10,
        losses=3,
        ko_rate=0.3,
        submission_rate=0.2,
        takedown_accuracy=0.4,
        takedown_defense=0.7,
        strikes_landed_per_min=4.2,
        strikes_absorbed_per_min=3.1,
        source="test",
    )
