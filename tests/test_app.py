from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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

        response = client.get("/predict")
        assert response.status_code == 200
        assert "Roster matchup" in response.text

        payload = {
            "a_name": "Alex Mercer",
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


def test_seeded_fighter_profiles_can_drive_prediction() -> None:
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
        assert "Alex Mercer" in response.text
        assert "Jordan Vale" in response.text
        assert "Find a fighter" in response.text

        response = client.get("/fighters/1")
        assert response.status_code == 200
        assert "Core profile" in response.text

        response = client.post(
            "/predict/from-profiles",
            data={"a_profile_id": 1, "b_profile_id": 2},
        )
        assert response.status_code == 200
        assert "Matchup outlook" in response.text


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
