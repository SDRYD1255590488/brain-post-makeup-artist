#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from audit import audit_html, source_counts
from common import Settings, authenticate_brain, sha256_text, write_json, write_text


def establish_support_session(settings: Settings) -> tuple[requests.Session, str]:
    """Establish BRAIN -> Support SSO using HTTP only, with no retries."""
    session = authenticate_brain(settings)
    exchange = session.get(
        f"{settings.brain_api_url}/authentication/support",
        timeout=60,
        allow_redirects=True,
    )
    if exchange.status_code != 200:
        raise RuntimeError(f"pure API support exchange failed with status {exchange.status_code}")
    bootstrap = session.get(
        f"{settings.support_url}/hc/{settings.locale}/community/topics",
        timeout=60,
    )
    if bootstrap.status_code != 200:
        raise RuntimeError(f"pure API support bootstrap failed with status {bootstrap.status_code}")
    session_response = session.get(
        f"{settings.support_url}/api/v2/help_center/sessions.json",
        timeout=60,
        headers={"Accept": "application/json"},
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
    if (output_dir / "operation-unknown.json").exists():
        raise RuntimeError("previous pure API create is unknown; inspect platform state first")
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
            write_json(output_dir / "operation-unknown.json", {"operation": "pure-api-create", "reason": type(exc).__name__})
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
        write_json(output_dir / "operation-unknown.json", {"operation": "pure-api-create", "reason": "success response lacked post identity"})
        raise RuntimeError("pure API create response lacks post identity")
    if urlparse(post_url).netloc not in {urlparse(settings.support_url).netloc, "worldquantbrain.zendesk.com"}:
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
