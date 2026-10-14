"""Database-backed authentication and account management for Jobflow."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from employment.database import SessionLocal
from employment.models import AuthSession, PasswordReset, UserAccount, UserProfile, utcnow
from backend.mailer import send_password_reset


router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE_NAME = "jobflow_session"
SESSION_DAYS = 1
REMEMBERED_SESSION_DAYS = 30
RESET_MINUTES = 30
MAX_AVATAR_BYTES = 5 * 1024 * 1024
AVATAR_ROOT = Path(__file__).resolve().parents[1] / "memory" / "avatars"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class AccountUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = Field(default=None, min_length=5, max_length=320)
    timezone: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=40)
    headline: str | None = Field(default=None, max_length=180)
    location: str | None = Field(default=None, max_length=180)
    bio: str | None = Field(default=None, max_length=1000)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


def _normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(422, "Enter a valid email address.")
    return email


def _validate_password(password: str) -> None:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(422, "Password must be at least 8 characters and include a letter and a number.")


def _password_hash(password: str) -> str:
    _validate_password(password)
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(expected)),
        )
        return hmac.compare_digest(derived.hex(), expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _set_session_cookie(response: Response, token: str, max_age: int) -> None:
    production = os.getenv("JOBFLOW_ENV", "development").lower() == "production"
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=production or os.getenv("JOBFLOW_SECURE_COOKIES", "false").lower() == "true",
        samesite="strict" if production else "lax",
        max_age=max_age,
        path="/",
    )


def _create_session(db, user_id: str, remember_me: bool) -> tuple[str, int]:
    token = secrets.token_urlsafe(48)
    days = REMEMBERED_SESSION_DAYS if remember_me else SESSION_DAYS
    max_age = days * 24 * 60 * 60
    db.add(AuthSession(user_id=user_id, token_hash=_token_hash(token), expires_at=utcnow() + timedelta(days=days)))
    return token, max_age


def current_user_id(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        raise HTTPException(401, "Authentication required.")
    now = utcnow()
    with SessionLocal.begin() as db:
        row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
        if row is None or _aware(row.expires_at) <= now:
            if row is not None:
                db.delete(row)
            raise HTTPException(401, "Your session has expired. Please sign in again.")
        account = db.get(UserAccount, row.user_id)
        if account is None or not account.active:
            db.delete(row)
            raise HTTPException(401, "This account is unavailable.")
        row.last_seen_at = now
        return row.user_id


def _account_view(db, user_id: str) -> dict[str, Any]:
    account = db.get(UserAccount, user_id)
    profile = db.get(UserProfile, user_id)
    if account is None or profile is None:
        raise HTTPException(404, "Account not found.")
    stored = dict(profile.profile or {})
    stored.update({"name": account.display_name, "email": account.email})
    avatar_version = int(_aware(account.updated_at).timestamp()) if account.updated_at else 0
    return {
        "user_id": user_id,
        "name": account.display_name,
        "email": account.email,
        "avatar_url": f"/api/auth/avatar?v={avatar_version}" if account.avatar_path else "",
        "locale": profile.locale,
        "country": profile.country,
        "profile": stored,
        "preferences": dict(profile.preferences or {}),
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


@router.post("/signup", status_code=201)
def signup(payload: SignupRequest, response: Response) -> dict[str, Any]:
    email = _normalize_email(payload.email)
    name = " ".join(payload.name.split())
    password_hash = _password_hash(payload.password)
    user_id = str(uuid.uuid4())
    try:
        with SessionLocal.begin() as db:
            if db.scalar(select(UserAccount).where(UserAccount.email == email)):
                raise HTTPException(409, "An account with this email already exists.")
            db.add(UserProfile(id=user_id, locale="en", country="EG", profile={"name": name, "email": email}, preferences={}))
            db.flush()
            db.add(UserAccount(user_id=user_id, email=email, password_hash=password_hash, display_name=name))
            db.flush()
            token, max_age = _create_session(db, user_id, remember_me=True)
        _set_session_cookie(response, token, max_age)
        with SessionLocal() as db:
            return _account_view(db, user_id)
    except IntegrityError as exc:
        raise HTTPException(409, "An account with this email already exists.") from exc


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    email = _normalize_email(payload.email)
    with SessionLocal.begin() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.email == email))
        if account is None or not account.active or not _password_matches(payload.password, account.password_hash):
            raise HTTPException(401, "Email or password is incorrect.")
        token, max_age = _create_session(db, account.user_id, payload.remember_me)
        user_id = account.user_id
    _set_session_cookie(response, token, max_age)
    with SessionLocal() as db:
        return _account_view(db, user_id)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        with SessionLocal.begin() as db:
            db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    with SessionLocal() as db:
        return _account_view(db, user_id)


@router.get("/session")
def session_status(request: Request) -> dict[str, Any]:
    """Check browser session state without turning an anonymous visit into a console error."""
    try:
        user_id = current_user_id(request)
    except HTTPException:
        return {"authenticated": False}
    with SessionLocal() as db:
        return {"authenticated": True, **_account_view(db, user_id)}


@router.patch("/account")
def update_account(payload: AccountUpdateRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    changes = payload.model_dump(exclude_none=True)
    try:
        with SessionLocal.begin() as db:
            account = db.get(UserAccount, user_id)
            profile = db.get(UserProfile, user_id)
            if account is None or profile is None:
                raise HTTPException(404, "Account not found.")
            stored = dict(profile.profile or {})
            if "email" in changes:
                email = _normalize_email(changes.pop("email"))
                owner = db.scalar(select(UserAccount).where(UserAccount.email == email, UserAccount.user_id != user_id))
                if owner:
                    raise HTTPException(409, "This email is already used by another account.")
                account.email = email
                stored["email"] = email
            if "name" in changes:
                name = " ".join(str(changes.pop("name")).split())
                account.display_name = name
                stored["name"] = name
            for key in ("timezone", "phone", "headline", "location", "bio"):
                if key in changes:
                    stored[key] = str(changes[key]).strip()
            profile.profile = stored
            profile.updated_at = utcnow()
            account.updated_at = utcnow()
        with SessionLocal() as db:
            return _account_view(db, user_id)
    except IntegrityError as exc:
        raise HTTPException(409, "This email is already used by another account.") from exc


def _avatar_type(content: bytes) -> tuple[str, str]:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise HTTPException(422, "Use a PNG, JPG, or WebP image.")


@router.post("/avatar")
async def upload_avatar(request: Request, avatar: UploadFile = File(...)) -> dict[str, Any]:
    user_id = current_user_id(request)
    content = await avatar.read(MAX_AVATAR_BYTES + 1)
    if not content:
        raise HTTPException(422, "Choose an image to upload.")
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "Profile images must be 5 MB or smaller.")
    extension, _ = _avatar_type(content)
    AVATAR_ROOT.mkdir(parents=True, exist_ok=True)
    target = AVATAR_ROOT / f"{user_id}.{extension}"
    previous = ""
    with SessionLocal.begin() as db:
        account = db.get(UserAccount, user_id)
        if account is None:
            raise HTTPException(404, "Account not found.")
        previous = account.avatar_path
        target.write_bytes(content)
        account.avatar_path = str(target)
        account.updated_at = utcnow()
    if previous and previous != str(target):
        old = Path(previous)
        if old.is_file() and old.parent.resolve() == AVATAR_ROOT.resolve():
            old.unlink(missing_ok=True)
    with SessionLocal() as db:
        return _account_view(db, user_id)


@router.get("/avatar")
def get_avatar(request: Request) -> FileResponse:
    user_id = current_user_id(request)
    with SessionLocal() as db:
        account = db.get(UserAccount, user_id)
        path = Path(account.avatar_path) if account and account.avatar_path else None
    if path is None or not path.is_file() or path.parent.resolve() != AVATAR_ROOT.resolve():
        raise HTTPException(404, "Profile image not found.")
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


@router.delete("/avatar")
def delete_avatar(request: Request) -> dict[str, bool]:
    user_id = current_user_id(request)
    previous = ""
    with SessionLocal.begin() as db:
        account = db.get(UserAccount, user_id)
        if account is None:
            raise HTTPException(404, "Account not found.")
        previous = account.avatar_path
        account.avatar_path = ""
        account.updated_at = utcnow()
    if previous:
        path = Path(previous)
        if path.is_file() and path.parent.resolve() == AVATAR_ROOT.resolve():
            path.unlink(missing_ok=True)
    return {"ok": True}


@router.post("/password/forgot")
def forgot_password(payload: ForgotPasswordRequest) -> dict[str, Any]:
    email = _normalize_email(payload.email)
    development_token = ""
    locale = "en"
    with SessionLocal.begin() as db:
        account = db.scalar(select(UserAccount).where(UserAccount.email == email))
        if account:
            token = secrets.token_urlsafe(40)
            development_token = token
            profile = db.get(UserProfile, account.user_id)
            locale = profile.locale if profile else "en"
            db.add(PasswordReset(user_id=account.user_id, token_hash=_token_hash(token), expires_at=utcnow() + timedelta(minutes=RESET_MINUTES)))
    result = {"message": "If an account exists, password reset instructions are ready."}
    if development_token:
        try:
            result["delivery"] = "sent" if send_password_reset(email, development_token, locale=locale) else "not_configured"
        except Exception:
            result["delivery"] = "failed"
    if development_token and os.getenv("JOBFLOW_ENV", "development") != "production":
        result["development_token"] = development_token
    return result


@router.post("/password/reset")
def reset_password(payload: ResetPasswordRequest) -> dict[str, str]:
    password_hash = _password_hash(payload.password)
    now = utcnow()
    with SessionLocal.begin() as db:
        reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _token_hash(payload.token), PasswordReset.used_at.is_(None)))
        if reset is None or _aware(reset.expires_at) <= now:
            raise HTTPException(422, "This reset link is invalid or has expired.")
        account = db.get(UserAccount, reset.user_id)
        if account is None:
            raise HTTPException(422, "This reset link is invalid or has expired.")
        account.password_hash = password_hash
        account.updated_at = now
        reset.used_at = now
        db.execute(delete(AuthSession).where(AuthSession.user_id == account.user_id))
    return {"message": "Password updated. You can sign in now."}
