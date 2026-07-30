from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_exposes_ollama_configuration_without_secret():
    response = client.get("/api/health")
    assert response.status_code == 200
    model = response.json()["model"]
    assert model["provider"].startswith("ollama_")
    assert "api_key" not in model


def test_cv_readiness_endpoint():
    response = client.post("/api/cv/readiness", json={"answers": {"identity": "One word"}})
    assert response.status_code == 200
    assert response.json()["ready"] is False


def test_invalid_model_provider_is_rejected():
    response = client.put(
        "/api/model-settings",
        json={"provider": "unknown", "base_url": "http://localhost:11434", "model": "x"},
    )
    assert response.status_code == 422
