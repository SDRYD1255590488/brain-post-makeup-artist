#!/usr/bin/env python3
from __future__ import annotations

from html import escape
from pathlib import Path

from playwright.async_api import async_playwright

from common import Settings, browser_launch_kwargs, write_json, write_text


VIEWPORTS = {
    "desktop": {"width": 1280, "height": 900},
    "tablet": {"width": 768, "height": 900},
    "mobile": {"width": 390, "height": 844},
}


def wrapper(body: str, title: str) -> str:
    safe_title = escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
body {{ margin: 0; background: #f4f5f7; color: #24292f; font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
.site {{ background: #123d37; color: white; padding: 14px 24px; font-weight: 700; }}
.shell {{ max-width: 960px; margin: 28px auto; padding: 0 18px; }}
.post {{ background: white; border: 1px solid #d8dee4; border-radius: 8px; padding: 28px; overflow-wrap: break-word; }}
.platform-title {{ margin: 0 0 20px; font-size: 32px; line-height: 1.25; }}
table, img {{ max-width: 100%; }}
pre {{ overflow: auto; }}
@media (max-width: 600px) {{ .shell {{ margin: 0; padding: 0; }} .post {{ border-radius: 0; border-left: 0; border-right: 0; padding: 18px; }} .platform-title {{ font-size: 26px; }} }}
</style>
</head>
<body><div class="site">BRAIN Forum Preview</div><main class="shell"><article class="post"><h1 class="platform-title">{safe_title}</h1><div class="post-body">{body}</div></article></main></body>
</html>
"""


async def create_preview(html_path: Path, output_dir: Path, title: str, *, screenshots: bool = True) -> dict[str, object]:
    body = html_path.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = output_dir / "rendered.html"
    write_text(rendered, wrapper(body, title))
    result: dict[str, object] = {"rendered_html": str(rendered), "screenshots": {}}
    if screenshots:
        settings = Settings.from_env(require_credentials=False)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                **browser_launch_kwargs(settings.chrome_channel, playwright.chromium.executable_path)
            )
            try:
                for name, viewport in VIEWPORTS.items():
                    page = await browser.new_page(viewport=viewport)
                    await page.goto(rendered.resolve().as_uri(), wait_until="load")
                    target = output_dir / f"{name}.png"
                    await page.screenshot(path=str(target), full_page=True)
                    result["screenshots"][name] = str(target)
                    await page.close()
            finally:
                await browser.close()
    write_json(output_dir / "preview.json", result)
    return result
