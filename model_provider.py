"""Runtime-selectable Ollama model provider for local and cloud models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any

import requests
from langchain_core.prompts import ChatPromptTemplate

from config import settings


_SETTINGS_PATH = Path(__file__).resolve().parent / "memory" / "model_settings.json"
_LOCK = RLock()


class ModelProviderError(RuntimeError):
    """A model endpoint is unavailable or incorrectly configured."""


def _normalise_base_url(value: str) -> str:
    return value.strip().rstrip("/")


class RuntimeModelSettings:
    def __init__(self) -> None:
        self.provider = settings.MODEL_PROVIDER
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self._api_key = settings.OLLAMA_API_KEY
        self._load()

    def _load(self) -> None:
        if not _SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.provider = str(data.get("provider") or self.provider)
        self.base_url = str(data.get("base_url") or self.base_url)
        self.model = str(data.get("model") or self.model)

    def public(self) -> dict[str, Any]:
        with _LOCK:
            return {
                "provider": self.provider,
                "base_url": self.base_url,
                "model": self.model,
                "api_key_configured": bool(self._api_key),
            }

    def update(self, provider: str, base_url: str, model: str, api_key: str | None = None) -> dict[str, Any]:
        if provider not in {"ollama_local", "ollama_cloud"}:
            raise ValueError("Provider must be ollama_local or ollama_cloud.")
        effective_url = _normalise_base_url(
            base_url or (settings.OLLAMA_CLOUD_URL if provider == "ollama_cloud" else settings.OLLAMA_BASE_URL)
        )
        if not effective_url.startswith(("http://", "https://")):
            raise ValueError("Ollama base URL must start with http:// or https://.")
        if provider == "ollama_cloud" and not (api_key or self._api_key):
            raise ValueError("An Ollama API key is required for direct cloud access.")
        with _LOCK:
            self.provider = provider
            self.base_url = effective_url
            self.model = model.strip()
            if api_key is not None:
                self._api_key = api_key.strip()
            _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_PATH.write_text(
                json.dumps(
                    {"provider": self.provider, "base_url": self.base_url, "model": self.model},
                    indent=2,
                ),
                encoding="utf-8",
            )
            return self.public()

    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


runtime_models = RuntimeModelSettings()


def list_models(
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    current = runtime_models.public()
    selected_provider = provider or str(current["provider"])
    selected_url = _normalise_base_url(
        base_url
        or str(current["base_url"])
        or (settings.OLLAMA_CLOUD_URL if selected_provider == "ollama_cloud" else settings.OLLAMA_BASE_URL)
    )
    headers = runtime_models.headers()
    if api_key is not None:
        if api_key.strip():
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        else:
            headers.pop("Authorization", None)
    try:
        response = requests.get(f"{selected_url}/api/tags", headers=headers, timeout=8)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        hint = "Start Ollama and retry." if selected_provider == "ollama_local" else "Check the cloud URL and API key."
        raise ModelProviderError(f"Could not reach Ollama at {selected_url}. {hint}") from exc
    models = []
    for item in payload.get("models", []):
        name = str(item.get("name") or item.get("model") or "").strip()
        if name:
            details = item.get("details") or {}
            models.append(
                {
                    "name": name,
                    "size": int(item.get("size") or 0),
                    "parameter_size": str(details.get("parameter_size") or ""),
                    "quantization": str(details.get("quantization_level") or ""),
                }
            )
    return sorted(models, key=lambda item: item["name"].casefold())


def invoke_prompt(
    prompt: ChatPromptTemplate,
    variables: dict[str, Any],
    *,
    json_mode: bool = False,
    timeout: int = 120,
) -> str:
    current = runtime_models.public()
    model = str(current["model"]).strip()
    if not model:
        raise ModelProviderError("No Ollama model is selected. Open Settings, refresh models, and choose one.")
    formatted = prompt.format_messages(**variables)
    messages = [{"role": message.type if message.type != "human" else "user", "content": str(message.content)} for message in formatted]
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    # Direct Ollama Cloud currently does not guarantee structured output.
    if json_mode and current["provider"] == "ollama_local":
        payload["format"] = "json"
    try:
        response = requests.post(
            f"{str(current['base_url']).rstrip('/')}/api/chat",
            headers=runtime_models.headers(),
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
    except (requests.RequestException, ValueError) as exc:
        raise ModelProviderError(f"Ollama request failed for model '{model}': {exc}") from exc
    if not str(content).strip():
        raise ModelProviderError(f"Ollama model '{model}' returned an empty response.")
    return str(content).strip()
