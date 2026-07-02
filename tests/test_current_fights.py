import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.media as media_module
from app.current_fights import import_current_fight_results
from app.database import Base
from app.media import (
    ImageHealth,
    commons_file_url,
    image_url_health,
    import_media_overrides,
    public_fighter_thumbnail,
    verify_media_urls,
)
from app.models import FightResult, FighterMedia, FighterProfile


def test_import_current_fight_results_upserts_missing_recent_bouts(tmp_path: Path) -> None:
    csv_path = tmp_path / "current.csv"
    csv_path.write_text(
        "\n".join(
            [
                "winner_name,loser_name,event_name,bout_date,method,promotion,weight_class,scheduled_rounds,finish_round,finish_time,source_url",
                "Justin Gaethje,Ilia Topuria,UFC Freedom 250,2026-06-14,TKO,UFC,Lightweight,5,2,3:45,https://example.com",
            ]
        ),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add_all(
            [
                profile("Justin Gaethje"),
                profile("Ilia Topuria"),
            ]
        )
        db.commit()

        imported = import_current_fight_results(db, csv_path)
        imported_again = import_current_fight_results(db, csv_path)
        result = db.scalar(select(FightResult).where(FightResult.winner_name == "Justin Gaethje"))

    assert imported == 1
    assert imported_again == 0
    assert result is not None
    assert result.bout_date == "2026-06-14"
    assert result.promotion == "UFC"
    assert result.weight_class == "Lightweight"
    assert result.scheduled_rounds == 5
    assert result.finish_round == 2
    assert result.finish_time == "3:45"


def test_import_media_overrides_replaces_bad_thumbnail(tmp_path: Path) -> None:
    csv_path = tmp_path / "media.csv"
    csv_path.write_text(
        "\n".join(
            [
                "fighter_name,thumbnail_url,page_url",
                "Justin Gaethje,https://ufc.com/justin.png,https://ufc.com/athlete/justin-gaethje",
            ]
        ),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(profile("Justin Gaethje"))
        db.add(
            FighterMedia(
                fighter_name="Justin Gaethje",
                thumbnail_url="https://commons.example/bad.jpg",
                source="wikidata-commons",
                status="found",
            )
        )
        db.commit()

        imported = import_media_overrides(db, csv_path)
        media = db.scalar(select(FighterMedia).where(FighterMedia.fighter_name == "Justin Gaethje"))

    assert imported == 1
    assert media.thumbnail_url == "https://ufc.com/justin.png"
    assert media.source == "curated-media-override"


def test_image_url_health_accepts_visible_png() -> None:
    health = image_url_health("https://example.com/fighter.png", opener=FakeImageResponse.open_png)

    assert health.valid is True
    assert health.width == 128
    assert health.height == 96


def test_image_url_health_rejects_tiny_or_non_image_payloads() -> None:
    tiny = image_url_health("https://example.com/tiny.png", opener=FakeImageResponse.open_tiny_png)
    html = image_url_health("https://example.com/not-image", opener=FakeImageResponse.open_html)

    assert tiny.valid is False
    assert tiny.reason == "too_small"
    assert html.valid is False
    assert html.reason == "not_image"


def test_commons_file_url_builds_thumbnail_from_wikidata_filename() -> None:
    url = commons_file_url("Justin Gaethje UFC 291.jpg")

    assert url == "https://commons.wikimedia.org/wiki/Special:FilePath/Justin_Gaethje_UFC_291.jpg?width=160"


def test_public_fighter_thumbnail_uses_wikidata_entity_image_when_summary_misses() -> None:
    thumbnail = public_fighter_thumbnail(
        "Justin Gaethje",
        opener=FakePublicImageResponses.open,
    )

    assert thumbnail == {
        "thumbnail_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Justin_Gaethje.jpg?width=160",
        "page_url": "https://en.wikipedia.org/wiki/Justin_Gaethje",
        "source": "wikidata-entity-image",
    }


def test_verify_media_urls_ignores_transient_fetch_failures(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(
        media_module,
        "image_url_health",
        lambda url: ImageHealth(valid=False, reason="fetch_failed"),
    )

    with Session() as db:
        db.add(
            FighterMedia(
                fighter_name="Sample Fighter",
                thumbnail_url="https://example.com/sample.jpg",
                source="wikidata-commons",
                status="found",
            )
        )
        db.commit()

        result = verify_media_urls(db, limit=1)
        media = db.scalar(select(FighterMedia).where(FighterMedia.fighter_name == "Sample Fighter"))

    assert result == {"checked": 1, "valid": 0, "broken": 0}
    assert media.status == "found"


def test_verify_media_urls_recovers_valid_broken_media(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(
        media_module,
        "image_url_health",
        lambda url: ImageHealth(valid=True, width=160, height=160),
    )

    with Session() as db:
        db.add(
            FighterMedia(
                fighter_name="Sample Fighter",
                thumbnail_url="https://example.com/sample.jpg",
                source="wikidata-commons",
                status="broken",
            )
        )
        db.commit()

        result = verify_media_urls(db, limit=1)
        media = db.scalar(select(FighterMedia).where(FighterMedia.fighter_name == "Sample Fighter"))

    assert result == {"checked": 1, "valid": 1, "broken": 0}
    assert media.status == "found"


def profile(name: str) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Lightweight",
        age=30,
        height_cm=180,
        reach_cm=182,
        wins=10,
        losses=3,
        ko_rate=0.3,
        submission_rate=0.2,
        takedown_accuracy=0.4,
        takedown_defense=0.7,
        strikes_landed_per_min=4.0,
        strikes_absorbed_per_min=3.0,
        source="test",
    )


class FakeImageResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]

    @staticmethod
    def open_png(request, timeout: int):
        return FakeImageResponse(png_header(128, 96), "image/png")

    @staticmethod
    def open_tiny_png(request, timeout: int):
        return FakeImageResponse(png_header(32, 32), "image/png")

    @staticmethod
    def open_html(request, timeout: int):
        return FakeImageResponse(b"<html></html>", "text/html")


def png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )


class FakePublicImageResponses:
    @staticmethod
    def open(request, timeout: int):
        url = request.full_url
        if "api/rest_v1/page/summary" in url:
            return FakeJsonResponse({"extract": "No image here."})
        if "wbsearchentities" in url:
            return FakeJsonResponse(
                {
                    "search": [
                        {
                            "id": "Q1",
                            "label": "Justin Gaethje",
                            "description": "American mixed martial artist",
                        }
                    ]
                }
            )
        if "wbgetentities" in url:
            return FakeJsonResponse(
                {
                    "entities": {
                        "Q1": {
                            "claims": {
                                "P18": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": "Justin Gaethje.jpg",
                                            }
                                        }
                                    }
                                ]
                            },
                            "sitelinks": {"enwiki": {"title": "Justin Gaethje"}},
                        }
                    }
                }
            )
        return FakeJsonResponse({})


class FakeJsonResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        body = json.dumps(self.payload).encode("utf-8")
        return body if size < 0 else body[:size]
