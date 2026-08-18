#!/usr/bin/env python3
"""Install the version-matched Chromium in this Skill's isolated cache."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from common import Settings


def main() -> None:
    settings = Settings.from_env(require_credentials=False)
    target = settings.playwright_browsers_path
    target.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(target)
    completed = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    # Do not trust a quiet/aborted installer: confirm the executable required by
    # this exact Python package exists in the same cache the runtime will use.
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        executable = Path(playwright.chromium.executable_path)
    finally:
        playwright.stop()
    if not executable.is_file():
        raise RuntimeError(
            "Playwright installer returned without the required Chromium executable; "
            f"inspect or clear the isolated cache at {target} before retrying"
        )
    print(json.dumps({
        "browser": "chromium",
        "cache": str(target),
        "executable": str(executable),
        "playwright": version("playwright"),
        "installed": True,
    }, indent=2))


if __name__ == "__main__":
    main()
