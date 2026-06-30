from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.ml.features import FighterFeatures
from app.ml.predictor import FightPredictor


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_homepage_promotion_cards_link_to_organization_sites() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'href="https://www.ufc.com/"' in response.text
    assert 'href="https://pflmma.com/"' in response.text
    assert 'href="https://www.onefc.com/"' in response.text
    assert 'href="https://invictafc.com/"' in response.text
    assert 'target="_blank"' in response.text
    assert 'rel="noopener noreferrer"' in response.text


def test_auth_and_prediction_flow() -> None:
    email = f"test-{uuid4()}@example.com"
    password = "good-password"

    with TestClient(app) as client:
        response = client.post(
            "/register",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/fighters"

        response = client.get("/predict")
        assert response.status_code == 200
        assert "Roster matchup" in response.text
        assert "Choose two fighters from the roster search to analyze." in response.text
        assert "Choose two fighters" in response.text
        assert "Include online sentiment" in response.text
        assert "Alex Mercer" not in response.text
        assert "Predict winner" not in response.text

        payload = {
            "a_name": "Alex Mercer",
            "a_weight_class": "Lightweight",
            "a_age": 29,
            "a_height_cm": 178,
            "a_reach_cm": 185,
            "a_wins": 15,
            "a_losses": 3,
            "a_ko_rate": 0.42,
            "a_submission_rate": 0.18,
            "a_takedown_accuracy": 0.46,
            "a_takedown_defense": 0.72,
            "a_strikes_landed_per_min": 4.8,
            "a_strikes_absorbed_per_min": 3.1,
            "b_name": "Jordan Vale",
            "b_weight_class": "Featherweight",
            "b_age": 32,
            "b_height_cm": 175,
            "b_reach_cm": 180,
            "b_wins": 13,
            "b_losses": 5,
            "b_ko_rate": 0.31,
            "b_submission_rate": 0.24,
            "b_takedown_accuracy": 0.41,
            "b_takedown_defense": 0.66,
            "b_strikes_landed_per_min": 3.9,
            "b_strikes_absorbed_per_min": 3.8,
        }
        response = client.post("/predict", data=payload)
        assert response.status_code == 200
        assert "Matchup outlook" in response.text
        assert "Key read" in response.text
        assert "Profile comparison" in response.text
        assert "Weight class" in response.text


def test_identical_profiles_do_not_produce_arbitrary_favorite() -> None:
    fighter_a = FighterFeatures(
        name="Fighter A",
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
    fighter_b = fighter_a.model_copy(update={"name": "Fighter B"})

    result = FightPredictor().predict(fighter_a, fighter_b)

    assert result["winner"] == "No clear edge"
    assert result["probability_a"] == 0.5
    assert result["probability_b"] == 0.5
    assert result["comparison_strength"] == "Limited"


def test_fighter_profiles_can_drive_prediction() -> None:
    email = f"profiles-{uuid4()}@example.com"
    password = "good-password"

    with TestClient(app) as client:
        response = client.post(
            "/register",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        assert response.status_code == 303

        response = client.get("/fighters")
        assert response.status_code == 200
        assert 'href="/fighters"' in response.text
        assert 'href="/predict"' in response.text
        assert 'href="/dashboard"' not in response.text
        assert 'href="/tree"' not in response.text
        assert "Find a fighter" in response.text
        assert "Page 1 of" in response.text
        assert "Next" in response.text

        response = client.get("/rankings")
        assert response.status_code == 200
        assert "Organization rankings" in response.text
        assert "UFC" in response.text
        assert "Open source" in response.text

        response = client.get("/odds-sites")
        assert response.status_code == 200
        assert "Betting odds sources" in response.text
        assert "DraftKings" in response.text
        assert "BestFightOdds" in response.text
        assert "not betting advice" in response.text
        assert 'target="_blank"' in response.text

        response = client.get("/fighters?page=2&limit=10")
        assert response.status_code == 200
        assert "Page 2 of" in response.text
        assert "Previous" in response.text

        response = client.get("/api/v1/fighters?limit=2")
        assert response.status_code == 200
        fighters = response.json()["fighters"]
        assert len(fighters) == 2

        response = client.get(f"/fighters/{fighters[0]['id']}")
        assert response.status_code == 200
        assert "Core profile" in response.text
        assert "Weight" in response.text
        assert "Career curve" in response.text
        assert "Victory count over time" in response.text
        assert "Fight history" in response.text
        assert "fighter-tree" in response.text
        assert "tree-expand-all" in response.text
        assert "/tree?" not in response.text
        assert "Recent coverage" in response.text
        assert "Recent coverage is not available right now." in response.text

        response = client.post(
            "/predict/from-profiles",
            data={"a_profile_id": fighters[0]["id"], "b_profile_id": fighters[1]["id"]},
        )
        assert response.status_code == 200
        assert "Matchup outlook" in response.text


def test_redundant_dashboard_and_tree_pages_are_removed() -> None:
    email = f"removed-pages-{uuid4()}@example.com"
    password = "good-password"

    with TestClient(app) as client:
        response = client.post(
            "/register",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        assert response.status_code == 303

        response = client.get("/tree")
        assert response.status_code == 404

        response = client.get("/dashboard")
        assert response.status_code == 404


def test_fighter_profile_uses_bounded_inline_tree(monkeypatch) -> None:
    email = f"profile-tree-{uuid4()}@example.com"
    password = "good-password"
    captured = {}

    def fake_tree(db, fighter, depth=4, max_children=80):
        captured["depth"] = depth
        captured["max_children"] = max_children
        return {
            "id": fighter.id,
            "name": fighter.name,
            "thumbnail_url": "/api/v1/fighter-thumbnail.svg?name=Test",
            "defeated": [],
        }

    monkeypatch.setattr(main_module, "build_defeat_tree", fake_tree)

    with TestClient(app) as client:
        response = client.post(
            "/register",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        assert response.status_code == 303

        response = client.get("/api/v1/fighters?search=Jon%20Jones&limit=1")
        fighter_id = response.json()["fighters"][0]["id"]

        response = client.get(f"/fighters/{fighter_id}")
        assert response.status_code == 200

    assert captured == {"depth": 2, "max_children": 10}


def test_public_api_lists_fighters_and_predicts() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/fighters?limit=2")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 2
        assert len(payload["fighters"]) == 2

        fighter_a = payload["fighters"][0]["id"]
        fighter_b = payload["fighters"][1]["id"]
        response = client.post(
            "/api/v1/predict",
            json={"fighter_a_id": fighter_a, "fighter_b_id": fighter_b},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["prediction"]["winner"]
        assert 0 <= result["prediction"]["probability_a"] <= 1
