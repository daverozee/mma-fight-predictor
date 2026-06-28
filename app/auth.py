import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

PBKDF2_ITERATIONS = 600_000


@dataclass(frozen=True)
class AuthResult:
    user: User | None
    error: str | None = None


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(digest, expected)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower().strip()))


def create_user(db: Session, email: str, password: str) -> AuthResult:
    normalized_email = email.lower().strip()
    if not normalized_email or "@" not in normalized_email:
        return AuthResult(user=None, error="Enter a valid email address.")
    if len(password) < 8:
        return AuthResult(user=None, error="Password must be at least 8 characters.")
    if get_user_by_email(db, normalized_email):
        return AuthResult(user=None, error="An account with that email already exists.")

    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResult(user=user)


def authenticate_user(db: Session, email: str, password: str) -> AuthResult:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return AuthResult(user=None, error="Invalid email or password.")
    return AuthResult(user=user)
