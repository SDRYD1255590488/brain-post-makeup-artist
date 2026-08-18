#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from common import EMAIL_RE, JWT_RE, SKILL_ROOT


CAPABILITIES_PATH = SKILL_ROOT / "references" / "capabilities.json"
PLACEHOLDER_RE = re.compile(r"(?i)(REPLACE_ME|TODO|IMAGE_PLACEHOLDER|YOUR_[A-Z_]+)")
CREDENTIAL_RE = re.compile(r"(?i)(authorization\s*:|cookie\s*:|csrf[_-]?token|password\s*[=:])")


def load_capabilities(path: Path = CAPABILITIES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_style(style: str) -> list[str]:
    return [part.split(":", 1)[0].strip().lower() for part in style.split(";") if ":" in part]


def source_counts(html: str) -> dict[str, int]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "images": len(soup.find_all("img")),
        "tables": len(soup.find_all("table")),
        "named_anchors": len(soup.find_all("a", attrs={"name": lambda value: bool(value)})),
        "hash_links": len(soup.select('a[href^="#"]')),
        "h2": len(soup.find_all("h2")),
        "h3": len(soup.find_all("h3")),
    }


def audit_html(html: str, *, title: str | None = None, forbidden_patterns: list[str] | None = None) -> dict[str, Any]:
    capabilities = load_capabilities()
    supported_tags = set(capabilities["tags"]["supported"])
    conditional_tags = set(capabilities["tags"].get("conditional", []))
    supported_styles = set(capabilities["style_properties"]["supported"])
    conditional_styles = set(capabilities["style_properties"].get("conditional", []))
    supported_attrs = set(capabilities["attributes"]["supported"])
    soup = BeautifulSoup(html, "html.parser")
    tags = list(soup.find_all(True))
    tag_names = {str(tag.name).lower() for tag in tags}
    unknown_tags = sorted(tag_names - supported_tags - conditional_tags)
    conditional_used = sorted(tag_names & conditional_tags)
    styles = {prop for tag in tags for prop in parse_style(str(tag.get("style") or ""))}
    unknown_styles = sorted(styles - supported_styles - conditional_styles)
    conditional_style_used = sorted(styles & conditional_styles)
    unknown_attrs: list[str] = []
    event_attrs: list[str] = []
    id_attrs: list[str] = []
    for tag in tags:
        for attr in tag.attrs:
            lowered = str(attr).lower()
            if lowered.startswith("on"):
                event_attrs.append(f"{tag.name}[{lowered}]")
            elif lowered == "id":
                id_attrs.append(f"{tag.name}#{tag.get(attr)}")
            elif lowered not in supported_attrs:
                unknown_attrs.append(f"{tag.name}[{lowered}]")
    images = [str(tag.get("src") or "") for tag in soup.find_all("img")]
    invalid_images = [src for src in images if not src.startswith("/hc/user_images/")]
    anchor_names = {str(tag.get("name")) for tag in soup.find_all("a", attrs={"name": True})}
    hash_targets = [str(tag.get("href"))[1:] for tag in soup.select('a[href^="#"]')]
    missing_targets = sorted({target for target in hash_targets if target and target not in anchor_names})
    visible = soup.get_text(" ", strip=True)
    secret_findings: list[str] = []
    if JWT_RE.search(html):
        secret_findings.append("JWT-like token")
    if CREDENTIAL_RE.search(html):
        secret_findings.append("credential-like field")
    if EMAIL_RE.search(visible):
        secret_findings.append("email address")
    forbidden_matches: dict[str, list[str]] = {}
    for pattern in forbidden_patterns or []:
        matches = re.findall(pattern, visible)
        if matches:
            forbidden_matches[pattern] = [str(item) for item in matches[:20]]
    errors: list[str] = []
    warnings: list[str] = []
    if unknown_tags:
        errors.append("unsupported tags: " + ", ".join(unknown_tags))
    if unknown_styles:
        errors.append("unsupported style properties: " + ", ".join(unknown_styles))
    if event_attrs:
        errors.append("event-handler attributes are forbidden")
    if invalid_images:
        errors.append("all images must use /hc/user_images/... paths")
    if id_attrs:
        errors.append("ordinary id attributes are stripped; use a[name]")
    if missing_targets:
        errors.append("missing named anchor targets: " + ", ".join(missing_targets))
    if secret_findings or forbidden_matches:
        errors.append("potentially sensitive visible content found")
    if PLACEHOLDER_RE.search(html):
        errors.append("unresolved placeholder found")
    if soup.find("h1"):
        warnings.append("body contains h1; platform title should be the only h1")
    if conditional_used:
        warnings.append("conditional tags used: " + ", ".join(conditional_used))
    if conditional_style_used:
        warnings.append("conditional styles used: " + ", ".join(conditional_style_used))
    if unknown_attrs:
        warnings.append("unverified attributes: " + ", ".join(sorted(set(unknown_attrs))))
    if title and title.strip() and soup.get_text(" ", strip=True).startswith(title.strip()):
        warnings.append("body appears to repeat the platform title")
    return {
        "ok": not errors,
        "html_bytes": len(html.encode("utf-8")),
        "visible_characters": len(visible),
        "counts": source_counts(html),
        "unknown_tags": unknown_tags,
        "unknown_styles": unknown_styles,
        "unknown_attributes": sorted(set(unknown_attrs)),
        "conditional_tags": conditional_used,
        "conditional_styles": conditional_style_used,
        "invalid_images": invalid_images,
        "id_attributes": id_attrs,
        "missing_anchor_targets": missing_targets,
        "secret_findings": secret_findings,
        "forbidden_matches": forbidden_matches,
        "errors": errors,
        "warnings": warnings,
    }
