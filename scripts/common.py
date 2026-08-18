#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
SENSITIVE_KEYS = {
    "account_id",
    "analytics_id",
    "authorization",
    "author_id",
    "cookie",
    "cookies",
    "csrf",
    "csrf_token",
    "current_password",
    "password",
    "secret",
    "security_token",
    "session",
    "session_token",
    "shared_csrf_token",
    "token",
    "user_id",
    "visitor_id",
    "x-csrf-token",
}
SENSITIVE_QUERY_KEYS = {
    "awsaccesskeyid",
    "credential",
    "expires",
    "signature",
    "token",
    "x-amz-algorithm",
    "x-amz-credential",
    "x-amz-date",
    "x-amz-expires",
    "x-amz-security-token",
    "x-amz-signature",
    "x-amz-signedheaders",
}
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
AUTH_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}")
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
COOKIE_RE = re.compile(r"(?i)(cookie|set-cookie)\s*:\s*[^\r\n]+")
PASSWORD_RE = re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*[^\s,;]+")


def load_env(path: Path | None = None) -> dict[str, str]:
    env_path = path or SKILL_ROOT / ".env"
    values: dict[str, str] = {}
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
                value = value[1:-1]
            values[key] = value
    for key, value in os.environ.items():
        if key.startswith("BRAIN_"):
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    email: str
    password: str
    brain_api_url: str
    support_url: str
    locale: str
    artifact_dir: Path
    chrome_channel: str

    @classmethod
    def from_env(cls, path: Path | None = None, require_credentials: bool = True) -> "Settings":
        values = load_env(path)
        email = values.get("BRAIN_EMAIL", "").strip()
        password = values.get("BRAIN_PASSWORD", "")
        if require_credentials and (not email or not password):
            raise RuntimeError("BRAIN_EMAIL and BRAIN_PASSWORD are required in .env")
        return cls(
            email=email,
            password=password,
            brain_api_url=values.get("BRAIN_API_URL", "https://api.worldquantbrain.com").rstrip("/"),
            support_url=values.get("BRAIN_SUPPORT_URL", "https://support.worldquantbrain.com").rstrip("/"),
            locale=values.get("BRAIN_FORUM_LOCALE", "en-us").strip("/"),
            artifact_dir=Path(values.get("BRAIN_FORUM_ARTIFACT_DIR", ".forum-runs")),
            chrome_channel=values.get("BRAIN_FORUM_CHROME_CHANNEL", "chromium"),
        )


def browser_launch_kwargs(channel: str, bundled_executable: str | Path | None = None) -> dict[str, Any]:
    """Select a browser without attempting a failed launch as a fallback probe."""
    kwargs: dict[str, Any] = {
        "headless": True,
        "args": ["--no-sandbox"],
    }
    normalized = channel.strip().lower()
    if normalized in {"", "auto"}:
        if bundled_executable and Path(bundled_executable).is_file():
            return kwargs
        kwargs["channel"] = "chrome"
        return kwargs
    if normalized and normalized not in {"chromium", "bundled", "playwright"}:
        kwargs["channel"] = channel
    elif bundled_executable is not None and not Path(bundled_executable).is_file():
        raise RuntimeError(
            "Playwright bundled Chromium is missing; run `uv run playwright install chromium` "
            "or set BRAIN_FORUM_CHROME_CHANNEL=chrome"
        )
    return kwargs


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc or not parts.query:
        return value
    safe_query = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        safe_query.append((key, "[REDACTED]" if key.lower() in SENSITIVE_QUERY_KEYS else item))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), parts.fragment))


def sanitize_text(value: str) -> str:
    value = JWT_RE.sub("[REDACTED_JWT]", value)
    value = AUTH_RE.sub(lambda match: f"{match.group(1)} [REDACTED]", value)
    value = COOKIE_RE.sub(lambda match: f"{match.group(1)}: [REDACTED]", value)
    value = PASSWORD_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    return re.sub(r"https?://[^\s\"'<>]+", lambda match: sanitize_url(match.group(0)), value)


def sanitize_data(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): sanitize_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_data(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_data(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_data(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, value: str, *, sanitize: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sanitize_text(value) if sanitize else value, encoding="utf-8")


def authenticate_brain(settings: Settings) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    response = session.post(
        f"{settings.brain_api_url}/authentication",
        auth=(settings.email, settings.password),
        timeout=60,
    )
    if response.status_code != 201:
        raise RuntimeError(f"BRAIN authentication failed with status {response.status_code}")
    status = session.get(f"{settings.brain_api_url}/authentication", timeout=30)
    if status.status_code not in {200, 201}:
        raise RuntimeError(f"BRAIN auth status check failed with status {status.status_code}")
    return session


def playwright_cookies(session: requests.Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cookie in session.cookies:
        row: dict[str, object] = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "secure": cookie.secure,
            "httpOnly": "HttpOnly" in cookie._rest,
            "sameSite": "Lax",
        }
        if cookie.expires:
            row["expires"] = cookie.expires
        rows.append(row)
    return rows
