#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from common import SKILL_ROOT, load_env


DEFAULT_CONFIG = Path.home() / "Library" / "Application Support" / "brain-mcp-v2" / "config.json"
SAFE_DEFAULTS = {
    "BRAIN_API_URL": "https://api.worldquantbrain.com",
    "BRAIN_SUPPORT_URL": "https://support.worldquantbrain.com",
    "BRAIN_FORUM_LOCALE": "en-us",
    "BRAIN_FORUM_ARTIFACT_DIR": ".forum-runs",
    "BRAIN_FORUM_CHROME_CHANNEL": "chromium",
    "BRAIN_FORUM_PROBE_POST_ID": "",
    "BRAIN_FORUM_PROBE_POST_URL": "",
}


def configure(config_path: Path, output_path: Path) -> dict[str, object]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    credentials = payload.get("credentials") or {}
    email = str(credentials.get("email") or "")
    password = str(credentials.get("password") or "")
    if not email or not password:
        raise RuntimeError("restricted config does not contain email/password credentials")
    existing = load_env(output_path)
    values = {**SAFE_DEFAULTS, **existing, "BRAIN_EMAIL": email, "BRAIN_PASSWORD": password}
    ordered = ["BRAIN_EMAIL", "BRAIN_PASSWORD", *SAFE_DEFAULTS]
    lines = [f"{key}={json.dumps(str(values.get(key, '')), ensure_ascii=False)}" for key in ordered]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, ("\n".join(lines) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)
    os.chmod(output_path, 0o600)
    return {"output": str(output_path), "configured": True, "mode": oct(output_path.stat().st_mode & 0o777)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Securely configure the Skill without printing credentials")
    parser.add_argument("--from-brain-mcp-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=SKILL_ROOT / ".env")
    args = parser.parse_args()
    print(json.dumps(configure(args.from_brain_mcp_config, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
