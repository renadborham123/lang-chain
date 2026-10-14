"""Secure integration helpers for OAuth providers and Telegram control."""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import os
import re
import secrets
import time
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import keyring

from .repository import LOCAL_USER_ID, EmploymentRepository, repository


_SERVICE = "jobflow"


class IntegrationService:
    def __init__(self, repo: EmploymentRepository | None = None) -> None:
        self.repo = repo or repository

    def oauth_authorization_url(self, provider: str, redirect_uri: str, user_id: str = LOCAL_USER_ID) -> dict[str, str]:
        if provider == "gmail":
            client_id = os.getenv("GOOGLE_CLIENT_ID", "")
            base = "https://accounts.google.com/o/oauth2/v2/auth"
            scope = "openid email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.events"
        elif provider == "outlook":
            client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
            tenant = os.getenv("MICROSOFT_TENANT_ID", "common")
            base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
            scope = "openid email offline_access Mail.Read Mail.Send Calendars.ReadWrite"
        else:
            raise ValueError("Provider must be gmail or outlook.")
        if not client_id:
            raise ValueError(f"{provider} OAuth client credentials are not configured.")
        state = secrets.token_urlsafe(32)
        keyring.set_password(_SERVICE, f"oauth-state:{user_id}:{provider}", state)
        params = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": scope, "state": state, "access_type": "offline", "prompt": "consent"}
        return {"provider": provider, "url": f"{base}?{urlencode(params)}", "state": state}

    async def oauth_callback(self, provider: str, *, code: str, state: str, redirect_uri: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        expected = keyring.get_password(_SERVICE, f"oauth-state:{user_id}:{provider}") or ""
        if not expected or not hmac.compare_digest(expected, state):
            raise ValueError("OAuth state is invalid or expired.")
        if provider == "gmail":
            token_url = "https://oauth2.googleapis.com/token"
            payload = {"client_id": os.getenv("GOOGLE_CLIENT_ID", ""), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""), "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri}
        elif provider == "outlook":
            tenant = os.getenv("MICROSOFT_TENANT_ID", "common")
            token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            payload = {"client_id": os.getenv("MICROSOFT_CLIENT_ID", ""), "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""), "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri}
        else:
            raise ValueError("Provider must be gmail or outlook.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            tokens = response.json()
        stored = {
            "access_token": tokens.get("access_token") or "",
            "refresh_token": tokens.get("refresh_token") or "",
            "expires_at": time.time() + int(tokens.get("expires_in") or 3600),
            "scope": tokens.get("scope") or "",
        }
        keyring.set_password(_SERVICE, f"oauth-token:{user_id}:{provider}", json.dumps(stored))
        keyring.delete_password(_SERVICE, f"oauth-state:{user_id}:{provider}")
        scopes = str(tokens.get("scope") or "").split()
        result = self.repo.update_integration(provider, {"status": "connected", "account_label": provider.title(), "scopes": scopes, "settings": {"token_type": tokens.get("token_type"), "expires_in": tokens.get("expires_in")}}, user_id=user_id)
        calendar_provider = "google_calendar" if provider == "gmail" else "outlook_calendar"
        self.repo.update_integration(calendar_provider, {"status": "connected", "account_label": f"{provider.title()} calendar", "scopes": scopes}, user_id=user_id)
        return result

    async def _access_token(self, provider: str, user_id: str = LOCAL_USER_ID) -> str:
        raw = keyring.get_password(_SERVICE, f"oauth-token:{user_id}:{provider}") or ""
        try:
            stored = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Reconnect {provider}; its saved token format is outdated.") from exc
        if stored.get("access_token") and float(stored.get("expires_at") or 0) > time.time() + 60:
            return str(stored["access_token"])
        refresh = str(stored.get("refresh_token") or "")
        if not refresh:
            raise ValueError(f"Reconnect {provider}; no refresh token is available.")
        if provider == "gmail":
            url = "https://oauth2.googleapis.com/token"
            payload = {"client_id": os.getenv("GOOGLE_CLIENT_ID", ""), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""), "refresh_token": refresh, "grant_type": "refresh_token"}
        elif provider == "outlook":
            tenant = os.getenv("MICROSOFT_TENANT_ID", "common")
            url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            payload = {"client_id": os.getenv("MICROSOFT_CLIENT_ID", ""), "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""), "refresh_token": refresh, "grant_type": "refresh_token", "scope": "openid email offline_access Mail.Read Mail.Send Calendars.ReadWrite"}
        else:
            raise ValueError("Provider must be gmail or outlook.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, data=payload)
            response.raise_for_status()
            tokens = response.json()
        stored.update({"access_token": tokens.get("access_token") or "", "refresh_token": tokens.get("refresh_token") or refresh, "expires_at": time.time() + int(tokens.get("expires_in") or 3600)})
        keyring.set_password(_SERVICE, f"oauth-token:{user_id}:{provider}", json.dumps(stored))
        return str(stored["access_token"])

    async def sync_recruiting_mail(self, provider: str, supervisor, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        token = await self._access_token(provider, user_id)
        headers = {"Authorization": f"Bearer {token}"}
        messages: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=25, headers=headers) as client:
            if provider == "gmail":
                listing = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"maxResults": 50, "q": "newer_than:30d (application OR interview OR assessment OR offer OR unfortunately)"})
                listing.raise_for_status()
                for item in (listing.json().get("messages") or []):
                    detail = await client.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}", params={"format": "full"})
                    detail.raise_for_status()
                    value = detail.json(); payload = value.get("payload") or {}; header_map = {str(h.get("name") or "").casefold(): str(h.get("value") or "") for h in payload.get("headers") or []}
                    messages.append({"id": str(value.get("id") or ""), "thread_id": str(value.get("threadId") or value.get("id") or ""), "subject": header_map.get("subject", ""), "sender": header_map.get("from", ""), "body": self._gmail_body(payload), "received": header_map.get("date", "")})
            elif provider == "outlook":
                since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
                response = await client.get("https://graph.microsoft.com/v1.0/me/messages", params={"$top": 50, "$select": "id,conversationId,subject,body,from,receivedDateTime", "$filter": f"receivedDateTime ge {since}", "$orderby": "receivedDateTime desc"})
                response.raise_for_status()
                for item in response.json().get("value") or []:
                    address = (((item.get("from") or {}).get("emailAddress") or {}).get("address") or "")
                    messages.append({"id": str(item.get("id") or ""), "thread_id": str(item.get("conversationId") or item.get("id") or ""), "subject": str(item.get("subject") or ""), "sender": address, "body": re.sub(r"<[^>]+>", " ", str((item.get("body") or {}).get("content") or "")), "received": str(item.get("receivedDateTime") or "")})
            else:
                raise ValueError("Provider must be gmail or outlook.")
        applications = self.repo.list_applications(user_id=user_id)
        ingested = transitioned = ambiguous = 0
        for message in messages:
            text = f"{message['subject']} {message['body']}".casefold()
            scores = []
            for application in applications:
                company = application.get("company", "").casefold().strip()
                title_tokens = {token for token in re.findall(r"[a-z0-9+#.]{3,}", application.get("title", "").casefold())}
                score = (4 if company and company in text else 0) + len(title_tokens & set(re.findall(r"[a-z0-9+#.]{3,}", text)))
                if score:
                    scores.append((score, application))
            scores.sort(key=lambda pair: pair[0], reverse=True)
            application = scores[0][1] if scores and (len(scores) == 1 or scores[0][0] > scores[1][0]) and scores[0][0] >= 2 else None
            _, created = self.repo.record_communication(provider=provider, external_id=message["id"], subject=message["subject"], participants={"sender": message["sender"]}, payload={"thread_id": message["thread_id"], "received": message["received"], "body_preview": message["body"][:1000]}, application_id=application.get("id") if application else None, user_id=user_id)
            if not created:
                continue
            ingested += 1
            result = supervisor.classify_recruiting_message(subject=message["subject"], body=message["body"], known_company=application.get("company", "") if application else "")
            mapping = {"rejected": "rejected", "interview": "interview", "offer": "offer", "reply": "recruiter_reply", "assessment": "screening"}
            if application and result.confidence >= .85:
                try:
                    self.repo.transition_application(application["id"], mapping[result.output["kind"]], source="communication_agent", message=f"Detected {result.output['kind']} from {provider}.", evidence={"communication_id": message["id"], "quote": result.output["evidence_quote"], "confidence": result.confidence}, user_id=user_id)
                    transitioned += 1
                except ValueError:
                    self.repo.create_approval(action_type="update_application_status", summary=f"Review detected {result.output['kind']} for {application['company']}", target_type="application", target_id=application["id"], payload={"status": mapping[result.output["kind"]], "communication_id": message["id"], "quote": result.output["evidence_quote"]}, user_id=user_id)
                    ambiguous += 1
            elif result.output.get("kind") != "reply":
                ambiguous += 1
        self.repo.update_integration(provider, {"status": "connected", "account_label": provider.title(), "settings": {"last_sync_count": ingested}}, user_id=user_id)
        return {"provider": provider, "checked": len(messages), "ingested": ingested, "transitioned": transitioned, "needs_review": ambiguous}

    async def send_email(self, provider: str, *, to: str, subject: str, body: str, user_id: str = LOCAL_USER_ID) -> str:
        if not to.strip():
            raise ValueError("Recipient email is required before sending.")
        token = await self._access_token(provider, user_id)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            if provider == "gmail":
                message = EmailMessage(); message["To"] = to; message["Subject"] = subject; message.set_content(body)
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
                response = await client.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", json={"raw": raw})
                response.raise_for_status(); return str(response.json().get("id") or "sent")
            if provider == "outlook":
                response = await client.post("https://graph.microsoft.com/v1.0/me/sendMail", json={"message": {"subject": subject, "body": {"contentType": "Text", "content": body}, "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": True})
                response.raise_for_status(); return str(response.headers.get("request-id") or "sent")
        raise ValueError("Provider must be gmail or outlook.")

    async def create_calendar_event(self, provider: str, event: dict[str, Any], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        """Create an approved calendar event and return its provider identity.

        The approval layer lives in the API so this helper can only be reached after
        the exact event payload has been reviewed. Provider tokens remain in keyring.
        """
        if provider not in {"gmail", "outlook"}:
            raise ValueError("Provider must be gmail or outlook.")
        title = str(event.get("title") or "").strip()
        start = str(event.get("start") or "").strip()
        end = str(event.get("end") or "").strip()
        timezone_name = str(event.get("timezone") or "Africa/Cairo").strip()
        if not title or not start or not end:
            raise ValueError("Calendar title, start, and end are required.")
        try:
            start_value = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_value = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Calendar start and end must be ISO-8601 date-times.") from exc
        if end_value <= start_value:
            raise ValueError("Calendar event must end after it starts.")
        token = await self._access_token(provider, user_id)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            if provider == "gmail":
                payload = {
                    "summary": title,
                    "description": str(event.get("description") or ""),
                    "location": str(event.get("location") or ""),
                    "start": {"dateTime": start, "timeZone": timezone_name},
                    "end": {"dateTime": end, "timeZone": timezone_name},
                }
                response = await client.post("https://www.googleapis.com/calendar/v3/calendars/primary/events", json=payload)
            else:
                payload = {
                    "subject": title,
                    "body": {"contentType": "Text", "content": str(event.get("description") or "")},
                    "location": {"displayName": str(event.get("location") or "")},
                    "start": {"dateTime": start, "timeZone": timezone_name},
                    "end": {"dateTime": end, "timeZone": timezone_name},
                }
                response = await client.post("https://graph.microsoft.com/v1.0/me/events", json=payload)
            response.raise_for_status()
            result = response.json()
        return {
            "provider": provider,
            "event_id": str(result.get("id") or "created"),
            "web_url": str(result.get("htmlLink") or result.get("webLink") or ""),
            "title": title,
            "start": start,
            "end": end,
        }

    @classmethod
    def _gmail_body(cls, payload: dict[str, Any]) -> str:
        body = str((payload.get("body") or {}).get("data") or "")
        if body:
            return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8", errors="replace")
        parts = payload.get("parts") or []
        plain = [part for part in parts if str(part.get("mimeType") or "") == "text/plain"]
        candidates = plain or parts
        return "\n".join(cls._gmail_body(part) for part in candidates if isinstance(part, dict))

    def configure_telegram(self, *, bot_token: str, chat_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("Telegram bot token and chat id are required.")
        try:
            bot_response = httpx.get(f"https://api.telegram.org/bot{bot_token.strip()}/getMe", timeout=10)
            bot_response.raise_for_status()
            bot = (bot_response.json().get("result") or {})
            chat_response = httpx.get(f"https://api.telegram.org/bot{bot_token.strip()}/getChat", params={"chat_id": chat_id.strip()}, timeout=10)
            chat_response.raise_for_status()
        except Exception as exc:
            raise ValueError("Telegram could not verify this bot token and chat ID.") from exc
        keyring.set_password(_SERVICE, f"telegram-token:{user_id}", bot_token.strip())
        bot_label = str(bot.get("username") or bot.get("first_name") or chat_id)
        return self.repo.update_integration("telegram", {"status": "connected", "account_label": f"Telegram · {bot_label}", "scopes": ["notify", "approve", "snooze", "mark_done"], "settings": {"chat_id": chat_id.strip()}}, user_id=user_id)

    async def send_telegram(self, *, title: str, body: str, buttons: list[dict[str, str]] | None = None, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        token = keyring.get_password(_SERVICE, f"telegram-token:{user_id}") or ""
        integration = next((item for item in self.repo.integration_status(user_id) if item["provider"] == "telegram"), None)
        chat_id = str((integration or {}).get("settings", {}).get("chat_id") or "")
        if not token or not chat_id:
            raise ValueError("Telegram is not configured.")
        keyboard = [[{"text": item["label"], "callback_data": item["callback_data"]}] for item in (buttons or [])]
        payload: dict[str, Any] = {"chat_id": chat_id, "text": f"<b>{title}</b>\n\n{body}", "parse_mode": "HTML", "disable_web_page_preview": True}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
            response.raise_for_status()
            return response.json()

    def poll_telegram_controls(self, user_id: str = LOCAL_USER_ID) -> int:
        token = keyring.get_password(_SERVICE, f"telegram-token:{user_id}") or ""
        integration = next((item for item in self.repo.integration_status(user_id) if item["provider"] == "telegram"), None)
        if not token or not integration or integration.get("status") != "connected":
            return 0
        settings = dict(integration.get("settings") or {})
        offset = int(settings.get("update_offset") or 0)
        response = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": offset, "timeout": 0, "allowed_updates": '["callback_query"]'}, timeout=8)
        response.raise_for_status()
        updates = response.json().get("result") or []
        processed = 0
        for update in updates:
            offset = max(offset, int(update.get("update_id") or 0) + 1)
            callback = update.get("callback_query") or {}
            callback_id = str(callback.get("id") or "")
            data = str(callback.get("data") or "")
            try:
                action, target_id = self.verify_callback(data)
                if action in {"done", "snooze"}:
                    self.repo.update_action(target_id, action, user_id=user_id)
                elif action in {"approve", "reject"}:
                    self.repo.decide_approval(target_id, "approved" if action == "approve" else "rejected", channel="telegram", user_id=user_id)
                else:
                    raise ValueError("Unsupported Telegram control.")
                text = "Action recorded in Wazzefni."
                processed += 1
            except Exception as exc:
                text = f"Could not apply that action: {exc}"
            if callback_id:
                httpx.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text[:180]}, timeout=8)
        if updates:
            settings["update_offset"] = offset
            self.repo.update_integration("telegram", {"status": "connected", "account_label": integration.get("account_label"), "scopes": integration.get("scopes"), "settings": settings}, user_id=user_id)
        return processed

    @staticmethod
    def signed_callback(action: str, target_id: str, *, ttl_seconds: int = 900) -> str:
        secret = os.getenv("JOBFLOW_CALLBACK_SECRET", "local-jobflow-secret-change-me")
        expires = int(time.time()) + ttl_seconds
        payload = f"{action}:{target_id}:{expires}"
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:20]
        return f"{payload}:{signature}"

    @staticmethod
    def verify_callback(value: str) -> tuple[str, str]:
        try:
            action, target_id, expires_raw, signature = value.split(":", 3)
            expires = int(expires_raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid Telegram callback.") from exc
        if expires < int(time.time()):
            raise ValueError("Telegram callback has expired.")
        secret = os.getenv("JOBFLOW_CALLBACK_SECRET", "local-jobflow-secret-change-me")
        payload = f"{action}:{target_id}:{expires}"
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:20]
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Telegram callback signature is invalid.")
        return action, target_id


integrations = IntegrationService()
