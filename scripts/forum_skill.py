#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import stat
import sys
from pathlib import Path

from audit import audit_html
from common import SKILL_ROOT, Settings, authenticate_brain, browser_launch_kwargs, configure_playwright_environment, write_json
from pure_api import pure_api_publish
from render import compose


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def doctor(args: argparse.Namespace) -> dict[str, object]:
    checks: dict[str, object] = {
        "python": sys.version.split()[0],
        "skill_root": str(SKILL_ROOT),
        "env_file": str(SKILL_ROOT / ".env"),
        "env_exists": (SKILL_ROOT / ".env").is_file(),
    }
    if (SKILL_ROOT / ".env").is_file():
        mode = stat.S_IMODE((SKILL_ROOT / ".env").stat().st_mode)
        checks["env_permissions"] = oct(mode)
        checks["env_permissions_safe"] = mode & 0o077 == 0
    settings = Settings.from_env(require_credentials=args.auth)
    checks["brain_api_url"] = settings.brain_api_url
    checks["support_url"] = settings.support_url
    checks["credentials_configured"] = bool(settings.email and settings.password)
    checks["playwright_browsers_path"] = str(settings.playwright_browsers_path)
    configure_playwright_environment(settings)
    if args.browser and args.auth:
        from platform import ForumBrowser

        async with ForumBrowser(settings) as client:
            await client.csrf()
        checks["browser"] = "ok"
        checks["authentication"] = "ok"
        checks["support_session"] = "ok"
    elif args.browser:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                **browser_launch_kwargs(
                    settings.chrome_channel,
                    playwright.chromium.executable_path,
                    headless=settings.headless,
                )
            )
            await browser.close()
        checks["browser"] = "ok"
    elif args.auth:
        session = authenticate_brain(settings)
        checks["authentication"] = "ok"
        session.close()
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose and safely publish BRAIN forum posts")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("doctor")
    command.add_argument("--browser", action="store_true")
    command.add_argument("--auth", action="store_true")

    command = sub.add_parser("compose")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--input-type", choices=["auto", "text", "markdown", "html"], default="auto")
    command.add_argument("--title", required=True)
    command.add_argument("--mode", choices=["preserve", "polish", "develop"], default="polish")
    command.add_argument("--theme", choices=["emerald", "indigo", "coral"], default="emerald")
    command.add_argument("--image-map", type=Path)
    command.add_argument("--no-navigation", action="store_true")
    command.add_argument("--output-dir", type=Path, required=True)

    command = sub.add_parser("audit")
    command.add_argument("--html", type=Path, required=True)
    command.add_argument("--title")
    command.add_argument("--forbid-regex", action="append", default=[])
    command.add_argument("--output", type=Path)
    command.add_argument("--strict", action="store_true")

    command = sub.add_parser("preview")
    command.add_argument("--html", type=Path, required=True)
    command.add_argument("--title", default="Forum preview")
    command.add_argument("--output-dir", type=Path, required=True)

    command = sub.add_parser("upload")
    command.add_argument("--manifest", type=Path, required=True)
    command.add_argument("--image-dir", type=Path, required=True)
    command.add_argument("--mapping", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--post-url")
    command.add_argument("--interval", type=float, default=0.35)
    command.add_argument("--limit", type=int, default=0)
    command.add_argument("--execute", action="store_true")

    for name in ("update", "probe"):
        command = sub.add_parser(name)
        command.add_argument("--post-id", required=True)
        command.add_argument("--confirm-post-id", required=True)
        command.add_argument("--confirm-current-sha256")
        command.add_argument("--post-url", required=True)
        command.add_argument("--html", type=Path, required=True)
        command.add_argument("--output-dir", type=Path, required=True)
        command.add_argument("--strict", action="store_true")
        command.add_argument("--execute", action="store_true")

    command = sub.add_parser("publish")
    command.add_argument("--html", type=Path, required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--confirm-title", required=True)
    command.add_argument("--topic-id", type=int, required=True)
    command.add_argument("--topic-name")
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--strict", action="store_true")
    command.add_argument("--execute", action="store_true")

    command = sub.add_parser("publish-source")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--confirm-title", required=True)
    command.add_argument("--topic-id", type=int, required=True)
    command.add_argument("--topic-name")
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--manifest", type=Path)
    command.add_argument("--image-dir", type=Path)
    command.add_argument("--mode", choices=["preserve", "polish", "develop"], default="polish")
    command.add_argument("--theme", choices=["emerald", "indigo", "coral"], default="emerald")
    command.add_argument("--browser-channel")
    command.add_argument("--strict", action="store_true")
    command.add_argument("--execute", action="store_true")

    command = sub.add_parser("verify")
    command.add_argument("--post-id", required=True)
    command.add_argument("--post-url", required=True)
    command.add_argument("--expected-html", type=Path)
    command.add_argument("--output-dir", type=Path, required=True)

    command = sub.add_parser("acceptance")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--confirm-title", required=True)
    command.add_argument("--topic-id", type=int, required=True)
    command.add_argument("--topic-name", required=True)
    command.add_argument("--manifest", type=Path, required=True)
    command.add_argument("--image-dir", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--mode", choices=["preserve", "polish", "develop"], default="polish")
    command.add_argument("--theme", choices=["emerald", "indigo", "coral"], default="emerald")
    command.add_argument("--browser-channel")
    command.add_argument("--execute", action="store_true")

    command = sub.add_parser("pure-api-publish")
    command.add_argument("--html", type=Path, required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--confirm-title", required=True)
    command.add_argument("--topic-id", type=int, required=True)
    command.add_argument("--topic-name", required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--strict", action="store_true")
    command.add_argument("--execute", action="store_true")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        emit(await doctor(args))
        return 0
    if args.command == "compose":
        emit(compose(args.input, args.title, args.output_dir, input_type=args.input_type, mode=args.mode, theme_name=args.theme, image_map_path=args.image_map, navigation=not args.no_navigation))
        return 0
    if args.command == "audit":
        result = audit_html(args.html.read_text(encoding="utf-8"), title=args.title, forbidden_patterns=args.forbid_regex)
        if args.output:
            write_json(args.output, result)
        emit(result)
        return 0 if result["ok"] and not (args.strict and result["warnings"]) else 1
    if args.command == "preview":
        from preview import create_preview

        emit(await create_preview(args.html, args.output_dir, args.title))
        return 0
    if args.command == "upload":
        from platform import upload_images

        if not args.execute:
            raise RuntimeError("dry-run protection: pass --execute to upload images")
        emit(await upload_images(args.manifest, args.image_dir, args.mapping, args.output_dir, interval=args.interval, limit=args.limit, post_url=args.post_url))
        return 0
    if args.command == "publish":
        from platform import publish_post

        if not args.execute:
            raise RuntimeError("dry-run protection: pass --execute to publish")
        emit(await publish_post(args.html, args.title, args.confirm_title, args.topic_id, args.topic_name, args.output_dir, strict=args.strict))
        return 0
    if args.command == "publish-source":
        from platform import publish_source

        if not args.execute:
            raise RuntimeError("dry-run protection: pass --execute to publish")
        emit(await publish_source(
            args.input,
            args.title,
            args.confirm_title,
            args.topic_id,
            args.topic_name,
            args.output_dir,
            mode=args.mode,
            theme=args.theme,
            browser_channel=args.browser_channel,
            strict=args.strict,
            manifest_path=args.manifest,
            image_dir=args.image_dir,
        ))
        return 0
    if args.command in {"update", "probe"}:
        from platform import update_post

        if not args.execute:
            raise RuntimeError("dry-run protection: pass --execute to access the update workflow")
        emit(await update_post(args.post_id, args.confirm_post_id, args.post_url, args.html, args.output_dir, strict=args.strict, confirm_current_sha256=args.confirm_current_sha256, probe=args.command == "probe"))
        return 0
    if args.command == "verify":
        from platform import ForumBrowser, verify_post

        settings = Settings.from_env()
        expected = args.expected_html.read_text(encoding="utf-8") if args.expected_html else None
        async with ForumBrowser(settings) as client:
            emit(await verify_post(client, args.post_id, args.post_url, args.output_dir, source_html=expected))
        return 0
    if args.command == "acceptance":
        from platform import run_acceptance

        if not args.execute:
            raise RuntimeError("dry-run protection: pass --execute to run live acceptance")
        emit(await run_acceptance(
            args.input,
            args.title,
            args.confirm_title,
            args.topic_id,
            args.topic_name,
            args.manifest,
            args.image_dir,
            args.output_dir,
            mode=args.mode,
            theme=args.theme,
            browser_channel=args.browser_channel,
        ))
        return 0
    if args.command == "pure-api-publish":
        if not args.execute:
            raise RuntimeError("dry-run protection: pass --execute to publish through the pure API path")
        emit(pure_api_publish(
            args.html,
            args.title,
            args.confirm_title,
            args.topic_id,
            args.topic_name,
            args.output_dir,
            strict=args.strict,
        ))
        return 0
    raise RuntimeError(f"unsupported command: {args.command}")


def main() -> None:
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(main_async(args)))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
