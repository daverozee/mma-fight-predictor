from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FighterProfile(Base):
    __tablename__ = "fighter_profiles"
    __table_args__ = (UniqueConstraint("name", name="uq_fighter_profiles_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    weight_class: Mapped[str] = mapped_column(String(80), nullable=False, default="Unknown")
    age: Mapped[float] = mapped_column(Float, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    reach_cm: Mapped[float] = mapped_column(Float, nullable=False)
    wins: Mapped[float] = mapped_column(Float, nullable=False)
    losses: Mapped[float] = mapped_column(Float, nullable=False)
    ko_rate: Mapped[float] = mapped_column(Float, nullable=False)
    submission_rate: Mapped[float] = mapped_column(Float, nullable=False)
    takedown_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    takedown_defense: Mapped[float] = mapped_column(Float, nullable=False)
    strikes_landed_per_min: Mapped[float] = mapped_column(Float, nullable=False)
    strikes_absorbed_per_min: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="sample")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FighterExternalFeature(Base):
    __tablename__ = "fighter_external_features"
    __table_args__ = (
        UniqueConstraint(
            "fighter_name",
            "feature_name",
            "source",
            name="uq_fighter_external_features_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fighter_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("fighter_profiles.id"),
        nullable=True,
        index=True,
    )
    fighter_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FighterMedia(Base):
    __tablename__ = "fighter_media"
    __table_args__ = (UniqueConstraint("fighter_name", name="uq_fighter_media_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fighter_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("fighter_profiles.id"),
        nullable=True,
        index=True,
    )
    fighter_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="generated-fallback")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="generated")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FightResult(Base):
    __tablename__ = "fight_results"
    __table_args__ = (
        UniqueConstraint(
            "winner_name",
            "loser_name",
            "event_name",
            "bout_date",
            "source",
            name="uq_fight_results_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    winner_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("fighter_profiles.id"),
        nullable=True,
        index=True,
    )
    loser_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("fighter_profiles.id"),
        nullable=True,
        index=True,
    )
    winner_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    loser_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bout_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceImportRun(Base):
    __tablename__ = "source_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_format: Mapped[str] = mapped_column(String(40), nullable=False)
    source_location: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="started")
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profiles_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profiles_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
