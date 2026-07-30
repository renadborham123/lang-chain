from config import settings


def test_placeholder_adzuna_values_are_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "your_app_id")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "your_app_key")
    assert settings.has_adzuna is False
