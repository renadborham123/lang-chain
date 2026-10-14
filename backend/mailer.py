"""Small SMTP adapter for transactional account email."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def send_password_reset(email: str, token: str, *, locale: str = "en") -> bool:
    if not smtp_configured():
        return False
    base_url = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:5173").rstrip("/")
    link = f"{base_url}/reset-password?{urlencode({'token': token})}"
    arabic = locale == "ar"
    message = EmailMessage()
    message["Subject"] = "استعادة كلمة مرور وظفني" if arabic else "Reset your Wazzefni password"
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = email
    message.set_content(
        (f"استخدم الرابط التالي لتعيين كلمة مرور جديدة. تنتهي صلاحيته قريبًا:\n\n{link}\n\nإذا لم تطلب ذلك فتجاهل الرسالة."
         if arabic else
         f"Use the link below to set a new password. It expires soon:\n\n{link}\n\nIf you did not request this, you can ignore this email.")
    )
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    with smtplib.SMTP(host, port, timeout=15) as client:
        if use_tls:
            client.starttls()
        if username:
            client.login(username, password)
        client.send_message(message)
    return True
