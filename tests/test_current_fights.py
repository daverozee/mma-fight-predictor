from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.current_fights import import_current_fight_results
from app.database import Base
from app.media import image_url_health, import_media_overrides
from app.models import FightResult, FighterMedia, FighterProfile


def test_import_current_fight_results_upserts_missing_recent_bouts(tmp_path: Path) -> None:
    csv_path = tmp_path / "current.csv"
    csv_path.write_text(
        "\n".join(
            [
                "winner_name,loser_name,event_name,bout_date,method,source_url",
                "Justin Gaethje,Ilia Topuria,UFC Freedom 250,2026-06-14,TKO,https://example.com",
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
