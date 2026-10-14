"""HTTP hardening that stays lightweight for local development."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityMiddleware(BaseHTTPMiddleware):
    _hits: dict[str, deque[float]] = defaultdict(deque)
    _lock = Lock()

    async def dispatch(self, request, call_next):
        production = os.getenv("JOBFLOW_ENV", "development").lower() == "production"
        force_https = production or os.getenv("JOBFLOW_FORCE_HTTPS", "false").lower() == "true"
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
        if force_https and request.url.scheme != "https" and forwarded_proto != "https":
            return RedirectResponse(str(request.url).replace("http://", "https://", 1), status_code=307)

        if request.url.path in {"/api/auth/login", "/api/auth/signup", "/api/auth/password/forgot", "/api/auth/password/reset"}:
            client = request.client.host if request.client else "unknown"
            key = f"{client}:{request.url.path}"
            now = time.monotonic()
            window = 300.0
            limit = int(os.getenv("JOBFLOW_AUTH_RATE_LIMIT", "20"))
            with self._lock:
                bucket = self._hits[key]
                while bucket and now - bucket[0] > window:
                    bucket.popleft()
                if len(bucket) >= limit:
                    return JSONResponse({"detail": "Too many attempts. Please wait a few minutes and try again."}, status_code=429, headers={"Retry-After": "300"})
                bucket.append(now)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
        if production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
