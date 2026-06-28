from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
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
