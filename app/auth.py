"""
Modul autentikasi session-based untuk Network Backup Manager.
Menggunakan itsdangerous untuk signed cookie + raw bcrypt (menggantikan passlib).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
import bcrypt
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.logging_config import get_logger
from app.models import User, UserRole

logger = get_logger(__name__)

# Session cookie name
SESSION_COOKIE = "nbm_session"


# ── Password helpers ────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash password menggunakan bcrypt murni (max 72 bytes)."""
    encoded = plain.encode('utf-8')
    if len(encoded) > 72:
        encoded = encoded[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(encoded, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verifikasi password dengan bcrypt murni."""
    encoded = plain.encode('utf-8')
    if len(encoded) > 72:
        encoded = encoded[:72]
    try:
        return bcrypt.checkpw(encoded, hashed.encode('utf-8'))
    except ValueError:
        return False


# ── Session helpers ─────────────────────────────────────────────────────────────

def _get_signer() -> TimestampSigner:
    return TimestampSigner(settings.session_secret_key)


def create_session(response, user_id: int) -> None:
    """Buat signed session cookie."""
    signer = _get_signer()
    token = signer.sign(str(user_id)).decode()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )


def clear_session(response) -> None:
    """Hapus session cookie."""
    response.delete_cookie(SESSION_COOKIE)


def get_user_id_from_request(request: Request) -> Optional[int]:
    """Ekstrak user ID dari signed cookie, return None jika invalid/expired."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        signer = _get_signer()
        user_id_bytes = signer.unsign(token, max_age=settings.session_max_age)
        return int(user_id_bytes.decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None


def get_current_user(request: Request) -> Optional[User]:
    """Dapatkan user yang sedang login, atau None."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        return None
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user and user.is_active:
            return user
    return None


def has_no_users() -> bool:
    """Cek apakah belum ada user sama sekali (first-run setup)."""
    with Session(engine) as session:
        count = session.exec(select(User)).first()
        return count is None


# ── Permission helpers ──────────────────────────────────────────────────────────

def require_auth(request: Request) -> Optional[User]:
    """
    Pastikan user sudah login.
    Jika belum, redirect ke /login.
    Digunakan sebagai dependency atau dipanggil manual di route handler.
    """
    user = get_current_user(request)
    if not user:
        return None
    return user


def is_admin(user: User) -> bool:
    return user.role == UserRole.admin


# ── Template context helper ─────────────────────────────────────────────────────

def auth_context(request: Request) -> dict:
    """Return dict {current_user, is_admin} untuk disertakan di template context."""
    user = get_current_user(request)
    return {
        "current_user": user,
        "is_admin": user is not None and is_admin(user),
    }
