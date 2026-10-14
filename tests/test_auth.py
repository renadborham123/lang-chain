from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.main import app
from employment.database import SessionLocal
from employment.models import AuthSession, PasswordReset, UserAccount, UserProfile


def test_account_session_profile_and_avatar_flow():
    client = TestClient(app)
    email = f"auth-{uuid4().hex}@example.com"
    password = "Jobflow123!"
    user_id = ""
    try:
        signup = client.post("/api/auth/signup", json={"name": "Auth Test", "email": email, "password": password})
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        assert signup.json()["email"] == email
        assert "httponly" in signup.headers["set-cookie"].lower()

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["name"] == "Auth Test"

        updated = client.patch("/api/auth/account", json={"headline": "Backend engineer", "location": "Cairo"})
        assert updated.status_code == 200
        assert updated.json()["profile"]["headline"] == "Backend engineer"

        profile = client.get("/api/profile")
        assert profile.status_code == 200
        assert profile.json()["user_id"] == user_id

        icon = Path(__file__).resolve().parents[1] / "frontend" / "public" / "jobflow-icon-192.png"
        with icon.open("rb") as image:
            avatar = client.post("/api/auth/avatar", files={"avatar": ("avatar.png", image, "image/png")})
        assert avatar.status_code == 200
        assert avatar.json()["avatar_url"].startswith("/api/auth/avatar")
        assert client.get(avatar.json()["avatar_url"]).status_code == 200

        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/login", json={"email": email, "password": "wrong-password", "remember_me": False}).status_code == 401
        assert client.post("/api/auth/login", json={"email": email, "password": password, "remember_me": False}).status_code == 200
    finally:
        if user_id:
            with SessionLocal.begin() as db:
                account = db.get(UserAccount, user_id)
                avatar_path = Path(account.avatar_path) if account and account.avatar_path else None
                db.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))
                db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
                if account:
                    db.delete(account)
                    db.flush()
                profile = db.get(UserProfile, user_id)
                if profile:
                    db.delete(profile)
            if avatar_path and avatar_path.is_file():
                avatar_path.unlink(missing_ok=True)


def test_profile_requires_authentication():
    client = TestClient(app)
    client.cookies.clear()
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/auth/session").json() == {"authenticated": False}
