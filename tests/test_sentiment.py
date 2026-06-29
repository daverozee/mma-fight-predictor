from app.ml.features import FighterFeatures
from app.ml.predictor import FightPredictor
from app.sentiment import sample_matchup_sentiment, sentiment_score


def test_sentiment_score_reads_positive_and_negative_terms() -> None:
    assert sentiment_score("dominant champion wins by knockout") > 0
    assert sentiment_score("injured after upset loss and missed weight") < 0


def test_sample_matchup_sentiment_uses_search_items() -> None:
    def fake_search(api_key: str, engine_id: str, query: str, results_per_fighter: int) -> list[dict]:
        if "Fighter A" in query:
            return [
                {
                    "title": "Fighter A earns dominant knockout win",
                    "snippet": "Healthy contender looks ready.",
                    "link": "https://example.com/a",
                }
            ]
        return [
            {
                "title": "Fighter B dealing with injury after loss",
                "snippet": "Recent coverage notes struggles.",
                "link": "https://example.com/b",
            }
        ]

    result = sample_matchup_sentiment(
        "Fighter A",
        "Fighter B",
        api_key="key",
        engine_id="engine",
        search_fn=fake_search,
    )

    assert result["available"] is True
    assert result["edge"] == "Fighter A"
    assert result["fighter_a"]["sample_size"] == 1


def test_predictor_applies_sentiment_as_bounded_nudge() -> None:
    fighter_a = profile("Fighter A")
    fighter_b = profile("Fighter B")
    sentiment = {
        "requested": True,
        "available": True,
        "sample_size": 2,
        "fighter_a": {"name": "Fighter A", "score": 1.0},
        "fighter_b": {"name": "Fighter B", "score": -1.0},
    }

    result = FightPredictor().predict(fighter_a, fighter_b, sentiment=sentiment)

    assert result["winner"] == "Fighter A"
    assert result["probability_a"] == 0.56
    assert result["sentiment"]["adjustment"] == 0.06


def profile(name: str) -> FighterFeatures:
    return FighterFeatures(
        name=name,
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
    )
