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
        "import_media_overrides",
        lambda db: calls.append(("media", None)) or 6,
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
        ("media", None),
    ]
    assert summary.records_seen == 12
    assert summary.profiles_promoted == 4
    assert summary.current_fights_imported == 5
    assert summary.media_overrides_imported == 6
    assert summary.fighters_in_db == 100
    assert summary.source_results == ["sample-source"]
