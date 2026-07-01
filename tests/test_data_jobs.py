from types import SimpleNamespace

from app import data_jobs


def test_run_data_import_cycle_collects_import_summary(monkeypatch) -> None:
    calls = []

    def fake_catalog(db, catalog_path):
        calls.append(("catalog", catalog_path))
        return SimpleNamespace(
            records_seen=12,
            profiles_created=2,
            profiles_updated=3,
            features_imported=40,
            sources=["sample-source"],
        )

    monkeypatch.setattr(data_jobs, "import_catalog", fake_catalog)
    monkeypatch.setattr(
        data_jobs,
        "promote_imported_fighters_to_profiles",
        lambda db: calls.append(("promote", None)) or 4,
    )
    monkeypatch.setattr(
        data_jobs,
        "import_current_fight_results",
        lambda db: calls.append(("current_fights", None)) or 5,
    )
    monkeypatch.setattr(
        data_jobs,
        "import_live_fight_results",
        lambda db, settings: calls.append(("live_fights", None))
        or {"seen": 8, "imported": 6, "skipped": 2},
    )
    monkeypatch.setattr(
        data_jobs,
        "import_configured_historical_fights",
        lambda db, settings: calls.append(("historical_fights", None)) or 9,
    )
    monkeypatch.setattr(
        data_jobs,
        "import_media_overrides",
        lambda db: calls.append(("media", None)) or 10,
    )
    monkeypatch.setattr(
        data_jobs,
        "improve_fighter_media",
        lambda db, seed_limit, wikimedia_limit, verification_limit: calls.append(
            ("improve_media", (seed_limit, wikimedia_limit, verification_limit))
        )
        or {
            "generated": 7,
            "wikimedia_checked": 8,
            "wikimedia_found": 9,
            "wikimedia_missing": 10,
            "verified": 11,
            "valid": 12,
            "broken": 13,
        },
    )
    monkeypatch.setattr(
        data_jobs,
        "ingestion_counts",
        lambda db: {"fighters": 100, "external_features": 200},
    )

    summary = data_jobs.run_data_import_cycle(object(), catalog_path="catalog.json")

    assert calls == [
        ("catalog", "catalog.json"),
        ("promote", None),
        ("current_fights", None),
        ("live_fights", None),
        ("historical_fights", None),
        ("media", None),
        ("improve_media", (500, 25, 50)),
    ]
    assert summary.records_seen == 12
    assert summary.profiles_promoted == 4
    assert summary.current_fights_imported == 5
    assert summary.live_fights_seen == 8
    assert summary.live_fights_imported == 6
    assert summary.live_fights_skipped == 2
    assert summary.historical_fights_imported == 9
    assert summary.media_overrides_imported == 10
    assert summary.media_improvement["generated"] == 7
    assert summary.media_improvement["broken"] == 13
    assert summary.fighters_in_db == 100
    assert summary.source_results == ["sample-source"]


def test_import_live_fight_results_skips_without_api_key() -> None:
    settings = SimpleNamespace(
        balldontlie_fights_import_enabled=True,
        balldontlie_api_key=None,
    )

    summary = data_jobs.import_live_fight_results(object(), settings)

    assert summary == {"seen": 0, "imported": 0, "skipped": 0}


def test_import_live_fight_results_uses_balldontlie_fights(monkeypatch) -> None:
    calls = []
    settings = SimpleNamespace(
        balldontlie_fights_import_enabled=True,
        balldontlie_api_key="key",
        balldontlie_fights_per_page=250,
        balldontlie_fights_max_pages=3,
        balldontlie_fights_pause_seconds=0.25,
    )

    monkeypatch.setattr(
        data_jobs,
        "iter_paginated",
        lambda **kwargs: calls.append(("fetch", kwargs)) or [{"id": 1}, {"id": 2}],
    )
    monkeypatch.setattr(
        data_jobs,
        "import_fight_edges",
        lambda db, fights, source: calls.append(("import", fights, source))
        or SimpleNamespace(fights_seen=2, imported=1, skipped=1),
    )

    summary = data_jobs.import_live_fight_results(object(), settings)

    assert summary == {"seen": 2, "imported": 1, "skipped": 1}
    assert calls[0][1]["params"] == {"per_page": 100}
    assert calls[0][1]["max_pages"] == 3
    assert calls[1][2] == data_jobs.BALLDONTLIE_FIGHTS_SOURCE
