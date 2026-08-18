#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from audit import audit_html, source_counts
from common import Settings, authenticate_brain, ensure_no_unknown_operation, sha256_text, write_json, write_operation_unknown, write_text


def establish_support_session(settings: Settings) -> tuple[requests.Session, str]:
    """Establish BRAIN -> Support SSO using HTTP only, with no retries."""
    # Bypass shell proxy settings for the BRAIN -> Zendesk SSO exchange. The
    # redirect chain writes the required cookies before its final Help Center
    # HTML page, which may itself be blocked with 403.
    session = authenticate_brain(settings, trust_env=False)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return_to = f"{settings.support_url}/hc/{settings.locale}/community/topics"
    exchange = session.get(
        f"{settings.brain_api_url}/authentication/support",
        params={"return_to": return_to},
        timeout=60,
        allow_redirects=False,
    )
    allowed_hosts = {
        urlparse(settings.brain_api_url).netloc,
        urlparse(settings.support_url).netloc,
        "worldquantbrain.zendesk.com",
    }
    for _ in range(12):
        if exchange.status_code not in {301, 302, 303, 307, 308}:
            break
        location = str(exchange.headers.get("Location") or "")
        if not location:
            raise RuntimeError("pure API support redirect is missing Location")
        next_url = urljoin(str(exchange.url), location)
        parsed = urlparse(next_url)
        if parsed.scheme != "https" or parsed.netloc not in allowed_hosts:
            raise RuntimeError("pure API support redirect returned an unexpected host")
        exchange = session.get(next_url, timeout=60, allow_redirects=False)
    else:
        raise RuntimeError("pure API support exchange exceeded the redirect limit")

    # Do not require the final HTML response to be 200. BRAIN Support may
    # return 403 for that page after the SSO cookies have already been set.
    # The session endpoint below is the authoritative authentication check.
    session_response = session.get(
        f"{settings.support_url}/api/v2/help_center/sessions.json",
        timeout=60,
        headers={"Accept": "application/json"},
        allow_redirects=False,
    )
    if session_response.status_code != 200:
        raise RuntimeError(f"pure API support session failed with status {session_response.status_code}")
    csrf = str((session_response.json().get("current_session") or {}).get("csrf_token") or "")
    if not csrf:
        raise RuntimeError("pure API support session did not return a CSRF token")
    return session, csrf


def request_headers(settings: Settings, csrf: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Origin": settings.support_url,
        "Referer": f"{settings.support_url}/hc/{settings.locale}/community/topics",
    }
    if csrf:
        headers.update(
            {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
    return headers


def pure_api_publish(
    html_path: Path,
    title: str,
    confirm_title: str,
    topic_id: int,
    topic_name: str,
    output_dir: Path,
    *,
    strict: bool,
) -> dict[str, Any]:
    if title != confirm_title:
        raise RuntimeError("confirmed title must exactly match the title")
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_no_unknown_operation(output_dir)
    marker = output_dir / "created-post.json"
    if marker.exists():
        raise RuntimeError("duplicate protection: this pure API run already created a post")
    html = html_path.read_text(encoding="utf-8")
    audit = audit_html(html, title=title)
    write_json(output_dir / "preflight.json", audit)
    write_text(output_dir / "submitted-source.html", html)
    if not audit["ok"] or (strict and audit["warnings"]):
        raise RuntimeError("pure API preflight audit failed")

    settings = Settings.from_env()
    session, csrf = establish_support_session(settings)
    topic_response = session.get(
        f"{settings.support_url}/api/v2/community/topics/{topic_id}.json",
        timeout=60,
        headers=request_headers(settings),
    )
    write_json(output_dir / "topic-response.json", {"status": topic_response.status_code})
    if topic_response.status_code != 200:
        raise RuntimeError(f"pure API topic lookup failed with status {topic_response.status_code}")
    topic = topic_response.json().get("topic") or {}
    if int(topic.get("id") or 0) != topic_id:
        raise RuntimeError("pure API resolved topic ID mismatch")
    if str(topic.get("name") or "") != topic_name:
        raise RuntimeError(f"pure API resolved topic name mismatch: {topic.get('name')!r}")

    dispatched = False
    try:
        dispatched = True
        response = session.post(
            f"{settings.support_url}/api/v2/community/posts.json",
            json={
                "post": {"topic_id": topic_id, "title": title, "details": html},
                "notify_subscribers": False,
            },
            headers=request_headers(settings, csrf),
            timeout=60,
        )
    except requests.RequestException as exc:
        if dispatched:
            write_operation_unknown(output_dir, {"operation": "pure-api-create", "reason": type(exc).__name__})
        raise RuntimeError("pure API create result is unknown; do not retry") from exc

    payload: dict[str, Any]
    try:
        payload = response.json()
    except ValueError:
        payload = {"body": response.text}
    write_json(output_dir / "create-response.json", {"status": response.status_code, "payload": payload})
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"pure API create failed with status {response.status_code}")
    post = payload.get("post") or {}
    post_id, post_url = str(post.get("id") or ""), str(post.get("html_url") or "")
    if not post_id.isdigit() or not post_url:
        write_operation_unknown(output_dir, {"operation": "pure-api-create", "reason": "success response lacked post identity"})
        raise RuntimeError("pure API create response lacks post identity")
    parsed_post_url = urlparse(post_url)
    if (
        parsed_post_url.scheme != "https"
        or parsed_post_url.netloc not in {urlparse(settings.support_url).netloc, "worldquantbrain.zendesk.com"}
        or re.fullmatch(rf"/hc/[^/]+/community/posts/{re.escape(post_id)}(?:-[^/]*)?/?", parsed_post_url.path) is None
    ):
        write_operation_unknown(output_dir, {"operation": "pure-api-create", "reason": "success response returned an invalid post identity"})
        raise RuntimeError("pure API create response returned an unexpected host")
    created = {
        "post_id": post_id,
        "post_url": post_url,
        "title": title,
        "topic_id": topic_id,
        "topic_name": topic.get("name"),
        "transport": "pure-http-api",
        "browser_used": False,
    }
    write_json(marker, created)

    readback = session.get(
        f"{settings.support_url}/api/v2/community/posts/{post_id}.json",
        timeout=60,
        headers=request_headers(settings),
    )
    readback_payload: dict[str, Any] = {}
    if readback.status_code == 200:
        readback_payload = readback.json().get("post") or {}
    elif readback.status_code == 404:
        internal = session.get(
            f"{settings.support_url}/hc/api/internal/communities/posts/{post_id}",
            timeout=60,
            headers=request_headers(settings),
        )
        if internal.status_code == 200:
            internal_payload = internal.json()
            readback_payload = internal_payload.get("post") or internal_payload
        write_json(output_dir / "internal-readback-response.json", {"status": internal.status_code})
    saved_html = str(readback_payload.get("details") or post.get("details") or "")
    readback_result = {
        "public_status": readback.status_code,
        "source_available": bool(saved_html),
        "source_sha256": sha256_text(saved_html) if saved_html else None,
        "source_counts": source_counts(saved_html) if saved_html else None,
        "expected_counts": source_counts(html),
    }
    if saved_html:
        write_text(output_dir / "readback-source.html", saved_html)
    write_json(output_dir / "readback.json", readback_result)
    created["readback"] = readback_result
    write_json(marker, created)
    return created
