#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from audit import audit_html, source_counts
from common import DEFAULT_USER_AGENT, Settings, authenticate_brain, browser_launch_kwargs, playwright_cookies, sha256_text, write_json, write_text
from render import compose


class ForumBrowser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "ForumBrowser":
        session = authenticate_brain(self.settings)
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            **browser_launch_kwargs(self.settings.chrome_channel, self.playwright.chromium.executable_path)
        )
        self.context = await self.browser.new_context(user_agent=DEFAULT_USER_AGENT)
        await self.context.add_cookies(playwright_cookies(session))
        self.page = await self.context.new_page()
        self.page.set_default_navigation_timeout(120_000)
        self.page.set_default_timeout(120_000)
        await self.page.goto(f"{self.settings.brain_api_url}/authentication/support", wait_until="domcontentloaded", timeout=120_000)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    @property
    def active_page(self) -> Page:
        if not self.page:
            raise RuntimeError("forum browser is not active")
        return self.page

    async def fetch_json(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None, csrf: str | None = None) -> dict[str, Any]:
        result = await self.active_page.evaluate(
            """async ({path, method, body, csrf}) => {
                const headers = {Accept: 'application/json'};
                if (body !== null) headers['Content-Type'] = 'application/json';
                if (csrf) {
                    headers['X-CSRF-Token'] = csrf;
                    headers['X-Requested-With'] = 'XMLHttpRequest';
                }
                const response = await fetch(path, {
                    method,
                    credentials: 'same-origin',
                    headers,
                    body: body === null ? undefined : JSON.stringify(body)
                });
                return {status: response.status, text: await response.text()};
            }""",
            {"path": path, "method": method, "body": body, "csrf": csrf},
        )
        return {"status": int(result["status"]), "text": str(result["text"])}

    async def csrf(self) -> str:
        result = await self.fetch_json("/api/v2/help_center/sessions.json")
        if result["status"] != 200:
            raise RuntimeError(f"support session failed with status {result['status']}")
        token = str((json.loads(result["text"]).get("current_session") or {}).get("csrf_token") or "")
        if not token:
            raise RuntimeError("support CSRF token is missing")
        return token

    async def resolve_topic(self, topic_id: int, topic_name: str | None = None) -> dict[str, Any]:
        await self.active_page.goto(f"{self.settings.support_url}/hc/{self.settings.locale}/community/topics/{topic_id}", wait_until="domcontentloaded")
        result = await self.fetch_json(f"/api/v2/community/topics/{topic_id}.json")
        if result["status"] != 200:
            raise RuntimeError(f"topic lookup failed with status {result['status']}")
        topic = json.loads(result["text"]).get("topic") or {}
        if int(topic.get("id") or 0) != topic_id:
            raise RuntimeError("resolved topic ID mismatch")
        if topic_name and str(topic.get("name")) != topic_name:
            raise RuntimeError(f"resolved topic name mismatch: {topic.get('name')!r}")
        return topic

    async def current_post(self, post_id: str, post_url: str) -> dict[str, Any]:
        await self.active_page.goto(post_url, wait_until="domcontentloaded")
        result = await self.fetch_json(f"/hc/api/internal/communities/posts/{post_id}")
        if result["status"] != 200:
            raise RuntimeError(f"current post lookup failed with status {result['status']}")
        payload = json.loads(result["text"])
        current = payload.get("post") or payload
        resolved = current.get("id")
        if resolved is not None and str(resolved) != str(post_id):
            raise RuntimeError("resolved post ID mismatch")
        if not current.get("title") or current.get("topic_id") is None:
            raise RuntimeError("current post is missing title or topic")
        return current


async def rendered_body(page: Page) -> tuple[str, str]:
    await page.wait_for_selector(".post-body, .article-body", timeout=120_000)
    body = page.locator(".post-body, .article-body").first
    return await body.inner_html(), await body.inner_text()


async def verify_post(client: ForumBrowser, post_id: str, post_url: str, output_dir: Path, *, source_html: str | None = None) -> dict[str, Any]:
    current = await client.current_post(post_id, post_url)
    page = client.active_page
    rendered_html, visible_text = await rendered_body(page)
    source = str(current.get("details") or "") or rendered_html
    result: dict[str, Any] = {
        "post_id": str(post_id),
        "post_url": post_url,
        "title": current.get("title"),
        "topic_id": current.get("topic_id"),
        "source_sha256": sha256_text(source),
        "rendered_sha256": sha256_text(rendered_html),
        "visible_sha256": sha256_text(visible_text),
        "source_counts": source_counts(source),
        "rendered_counts": source_counts(rendered_html),
    }
    if source_html is not None:
        expected = source_counts(source_html)
        result["expected_sha256"] = sha256_text(source_html)
        result["expected_counts"] = expected
        result["count_mismatches"] = {
            key: {"expected": value, "actual": result["rendered_counts"][key]}
            for key, value in expected.items()
            if result["rendered_counts"][key] != value
        }
    write_text(output_dir / "source.html", source)
    write_text(output_dir / "rendered.html", rendered_html)
    write_text(output_dir / "visible.txt", visible_text, sanitize=True)
    write_json(output_dir / "metadata.json", result)
    await page.screenshot(path=str(output_dir / "rendered.png"), full_page=True)
    return result


async def upload_images_with_client(client: ForumBrowser, manifest_path: Path, image_dir: Path, mapping_path: Path, output_dir: Path, *, interval: float, limit: int, post_url: str | None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise RuntimeError("image manifest must be a JSON list")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.exists() else {}
    pending: list[dict[str, str]] = []
    for row in manifest:
        key, filename = str(row.get("key") or ""), str(row.get("filename") or "")
        if not key or not filename:
            raise RuntimeError("every image row needs key and filename")
        if not str(mapping.get(key) or mapping.get(filename) or "").startswith("/hc/user_images/"):
            pending.append({"key": key, "filename": filename})
    if limit > 0:
        pending = pending[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_unknown = output_dir / "upload-unknown.json"
    if upload_unknown.exists():
        raise RuntimeError("a previous image registration is unknown; inspect the editor before retrying")
    events: list[dict[str, Any]] = []
    page = client.active_page
    settings = client.settings
    if post_url:
        await page.goto(post_url, wait_until="domcontentloaded")
        await page.get_by_role("button", name="Post actions").click()
        await page.get_by_role("menuitem", name="Edit").click()
        await page.wait_for_selector('[role="dialog"]')
        file_input = page.locator('[role="dialog"] input[type="file"][accept*="image"]')
    else:
        await page.goto(f"{settings.support_url}/hc/{settings.locale}/community/posts/new", wait_until="domcontentloaded")
        file_input = page.locator('#hc-wysiwyg input[type="file"][accept*="image"]')
    if await file_input.count() != 1:
        raise RuntimeError("the forum image input was not found; editor structure may have changed")
    for index, row in enumerate(pending, start=1):
        image_path = image_dir / row["filename"]
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        dispatched = False
        try:
            async with page.expect_response(
                lambda response: response.request.method == "POST" and response.url.rstrip("/").endswith("/api/v2/guide/user_images"),
                timeout=120_000,
            ) as registration:
                dispatched = True
                await file_input.set_input_files(str(image_path.resolve()))
            response = await registration.value
        except Exception as exc:
            if dispatched:
                write_json(upload_unknown, {"filename": row["filename"], "reason": type(exc).__name__})
            raise
        if response.status not in {200, 201}:
            raise RuntimeError(f"image registration failed for {image_path.name}: {response.status}")
        payload = await response.json()
        user_path = str((payload.get("user_image") or {}).get("path") or "")
        if not user_path.startswith("/hc/user_images/"):
            write_json(upload_unknown, {"filename": row["filename"], "reason": "registration response lacked final User Image path"})
            raise RuntimeError(f"invalid User Image path for {image_path.name}")
        mapping[row["key"]] = user_path
        mapping[row["filename"]] = user_path
        events.append({"index": index, "key": row["key"], "filename": row["filename"], "path": user_path})
        write_json(mapping_path, mapping)
        write_json(output_dir / "upload-state.json", events)
        if index < len(pending):
            await page.wait_for_timeout(int(max(interval, 0) * 1000))
    result = {"uploaded": len(events), "mapping": str(mapping_path), "pending_before": len(pending)}
    write_json(output_dir / "upload-result.json", result)
    return result


async def upload_images(manifest_path: Path, image_dir: Path, mapping_path: Path, output_dir: Path, *, interval: float, limit: int, post_url: str | None) -> dict[str, Any]:
    settings = Settings.from_env()
    async with ForumBrowser(settings) as client:
        return await upload_images_with_client(client, manifest_path, image_dir, mapping_path, output_dir, interval=interval, limit=limit, post_url=post_url)


def ensure_write_directory(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "operation_unknown.json").exists():
        raise RuntimeError("a previous operation is unknown; verify platform state before another write")


async def publish_post(html_path: Path, title: str, confirm_title: str, topic_id: int, topic_name: str | None, output_dir: Path, *, strict: bool) -> dict[str, Any]:
    if title != confirm_title:
        raise RuntimeError("confirmed title must exactly match the title")
    ensure_write_directory(output_dir)
    marker = output_dir / "created-post.json"
    if marker.exists():
        raise RuntimeError("duplicate protection: this output directory already records a successful create")
    html = html_path.read_text(encoding="utf-8")
    audit = audit_html(html, title=title)
    write_json(output_dir / "preflight.json", audit)
    write_text(output_dir / "submitted-source.html", html)
    if not audit["ok"] or (strict and audit["warnings"]):
        raise RuntimeError("preflight audit failed")
    settings = Settings.from_env()
    dispatched = False
    async with ForumBrowser(settings) as client:
        topic = await client.resolve_topic(topic_id, topic_name)
        csrf = await client.csrf()
        try:
            dispatched = True
            response = await client.fetch_json(
                "/api/v2/community/posts.json",
                method="POST",
                csrf=csrf,
                body={"post": {"title": title, "details": html, "topic_id": topic_id}, "notify_subscribers": False},
            )
        except Exception as exc:
            if dispatched:
                write_json(output_dir / "operation_unknown.json", {"operation": "create", "reason": type(exc).__name__})
            raise
        parsed = json.loads(response["text"]) if response["text"].strip().startswith("{") else {"body": response["text"]}
        write_json(output_dir / "create-response.json", {"status": response["status"], "payload": parsed})
        if response["status"] not in {200, 201}:
            raise RuntimeError(f"post creation failed with status {response['status']}")
        post = parsed.get("post") or {}
        post_id, post_url = str(post.get("id") or ""), str(post.get("html_url") or "")
        if not post_id.isdigit() or not post_url:
            write_json(output_dir / "operation_unknown.json", {"operation": "create", "reason": "success response lacked post identity"})
            raise RuntimeError("create response lacks a post ID or URL")
        if urlparse(post_url).netloc not in {urlparse(settings.support_url).netloc, "worldquantbrain.zendesk.com"}:
            raise RuntimeError("create response returned an unexpected host")
        created: dict[str, Any] = {"post_id": post_id, "post_url": post_url, "title": title, "topic_id": topic_id, "topic_name": topic.get("name")}
        write_json(marker, created)
        created["verification"] = await verify_post(client, post_id, post_url, output_dir / "readback", source_html=html)
        write_json(marker, created)
        return created


async def update_post(post_id: str, confirm_post_id: str, post_url: str, html_path: Path, output_dir: Path, *, strict: bool, confirm_current_sha256: str | None, probe: bool = False) -> dict[str, Any]:
    if str(post_id) != str(confirm_post_id):
        raise RuntimeError("confirmed Post ID must exactly match the target")
    ensure_write_directory(output_dir)
    html = html_path.read_text(encoding="utf-8")
    audit = audit_html(html)
    write_json(output_dir / "preflight.json", audit)
    write_text(output_dir / "submitted-source.html", html)
    if not audit["ok"] or (strict and audit["warnings"]):
        raise RuntimeError("preflight audit failed")
    settings = Settings.from_env()
    async with ForumBrowser(settings) as client:
        current = await client.current_post(post_id, post_url)
        current_html = str(current.get("details") or "")
        current_sha = sha256_text(current_html)
        write_text(output_dir / "before-source.html", current_html)
        write_json(output_dir / "before-metadata.json", {"post_id": post_id, "title": current.get("title"), "topic_id": current.get("topic_id"), "source_sha256": current_sha, "probe": probe})
        if not confirm_current_sha256:
            raise RuntimeError(f"read-only preflight complete; rerun with --confirm-current-sha256 {current_sha}")
        if confirm_current_sha256 != current_sha:
            raise RuntimeError("confirmed current-source SHA-256 does not match the platform")
        csrf = await client.csrf()
        dispatched = False
        try:
            dispatched = True
            response = await client.fetch_json(
                f"/hc/api/internal/communities/posts/{post_id}",
                method="PUT",
                csrf=csrf,
                body={"post": {"title": current["title"], "details": html, "topic_id": current["topic_id"]}},
            )
        except Exception as exc:
            if dispatched:
                write_json(output_dir / "operation_unknown.json", {"operation": "probe" if probe else "update", "post_id": post_id, "reason": type(exc).__name__})
            raise
        parsed = json.loads(response["text"]) if response["text"].strip().startswith("{") else {"body": response["text"]}
        write_json(output_dir / "update-response.json", {"status": response["status"], "payload": parsed})
        if response["status"] not in {200, 201}:
            raise RuntimeError(f"post update failed with status {response['status']}")
        verification = await verify_post(client, post_id, post_url, output_dir / "readback", source_html=html)
        result = {"post_id": post_id, "post_url": post_url, "probe": probe, "before_sha256": current_sha, "after": verification}
        write_json(output_dir / "updated-post.json", result)
        return result


def acceptance_update_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    callout = soup.new_tag("aside")
    callout["style"] = "background-color: #EEF2FF; border-left: 4px solid #4338CA; padding: 12px;"
    strong = soup.new_tag("strong")
    label = soup.new_tag("span")
    label["style"] = "color: #3730A3;"
    label.string = "Update verification:"
    strong.append(label)
    callout.append(strong)
    callout.append(" the same acceptance post was updated exactly once.")
    soup.append(callout)
    return str(soup).strip() + "\n"


async def run_acceptance(
    input_path: Path,
    title: str,
    confirm_title: str,
    topic_id: int,
    topic_name: str,
    manifest_path: Path,
    image_dir: Path,
    output_dir: Path,
    *,
    mode: str,
    theme: str,
    browser_channel: str,
) -> dict[str, Any]:
    """Run one retained create and one update in a single browser process."""
    if title != confirm_title:
        raise RuntimeError("confirmed title must exactly match the title")
    if not title.startswith("[SKILL ACCEPTANCE]"):
        raise RuntimeError("acceptance title must start with [SKILL ACCEPTANCE]")
    ensure_write_directory(output_dir)
    marker = output_dir / "acceptance-result.json"
    if marker.exists():
        raise RuntimeError("duplicate protection: this acceptance run already completed")
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = replace(Settings.from_env(), chrome_channel=browser_channel)
    mapping_path = output_dir / "image-map.json"
    draft_dir = output_dir / "draft"
    dispatched_create = False
    dispatched_update = False

    async with ForumBrowser(settings) as client:
        await client.resolve_topic(topic_id, topic_name)
        upload_result = await upload_images_with_client(
            client,
            manifest_path,
            image_dir,
            mapping_path,
            output_dir / "upload",
            interval=0.35,
            limit=1,
            post_url=None,
        )
        compose(
            input_path,
            title,
            draft_dir,
            mode=mode,
            theme_name=theme,
            image_map_path=mapping_path,
            navigation=True,
        )
        html_path = draft_dir / "post.html"
        html = html_path.read_text(encoding="utf-8")
        audit = audit_html(html, title=title)
        write_json(output_dir / "create-preflight.json", audit)
        if not audit["ok"] or audit["warnings"]:
            raise RuntimeError("acceptance create preflight must have zero errors and warnings")

        topic = await client.resolve_topic(topic_id, topic_name)
        csrf = await client.csrf()
        try:
            dispatched_create = True
            response = await client.fetch_json(
                "/api/v2/community/posts.json",
                method="POST",
                csrf=csrf,
                body={"post": {"title": title, "details": html, "topic_id": topic_id}, "notify_subscribers": False},
            )
        except Exception as exc:
            if dispatched_create:
                write_json(output_dir / "operation_unknown.json", {"operation": "acceptance-create", "reason": type(exc).__name__})
            raise
        parsed = json.loads(response["text"]) if response["text"].strip().startswith("{") else {"body": response["text"]}
        write_json(output_dir / "create-response.json", {"status": response["status"], "payload": parsed})
        if response["status"] not in {200, 201}:
            raise RuntimeError(f"acceptance create failed with status {response['status']}")
        post = parsed.get("post") or {}
        post_id, post_url = str(post.get("id") or ""), str(post.get("html_url") or "")
        if not post_id.isdigit() or not post_url:
            write_json(output_dir / "operation_unknown.json", {"operation": "acceptance-create", "reason": "success response lacked post identity"})
            raise RuntimeError("acceptance create response lacks post identity")
        created = {"post_id": post_id, "post_url": post_url, "title": title, "topic_id": topic_id, "topic_name": topic.get("name")}
        write_json(output_dir / "created-post.json", created)
        create_readback = await verify_post(client, post_id, post_url, output_dir / "create-readback", source_html=html)

        updated_html = acceptance_update_html(html)
        update_audit = audit_html(updated_html)
        write_text(output_dir / "updated-source.html", updated_html)
        write_json(output_dir / "update-preflight.json", update_audit)
        if not update_audit["ok"] or update_audit["warnings"]:
            raise RuntimeError("acceptance update preflight must have zero errors and warnings")
        current = await client.current_post(post_id, post_url)
        before_sha = sha256_text(str(current.get("details") or ""))
        csrf = await client.csrf()
        try:
            dispatched_update = True
            update_response = await client.fetch_json(
                f"/hc/api/internal/communities/posts/{post_id}",
                method="PUT",
                csrf=csrf,
                body={"post": {"title": current["title"], "details": updated_html, "topic_id": current["topic_id"]}},
            )
        except Exception as exc:
            if dispatched_update:
                write_json(output_dir / "operation_unknown.json", {"operation": "acceptance-update", "post_id": post_id, "reason": type(exc).__name__})
            raise
        update_parsed = json.loads(update_response["text"]) if update_response["text"].strip().startswith("{") else {"body": update_response["text"]}
        write_json(output_dir / "update-response.json", {"status": update_response["status"], "payload": update_parsed})
        if update_response["status"] not in {200, 201}:
            raise RuntimeError(f"acceptance update failed with status {update_response['status']}")
        update_readback = await verify_post(client, post_id, post_url, output_dir / "update-readback", source_html=updated_html)
        rendered_update = (output_dir / "update-readback" / "rendered.html").read_text(encoding="utf-8")
        if "Update verification:" not in rendered_update:
            raise RuntimeError("acceptance update marker is missing from rendered readback")

        result = {
            **created,
            "browser_processes": 1,
            "image_upload": upload_result,
            "image_paths_valid": all(str(value).startswith("/hc/user_images/") for value in json.loads(mapping_path.read_text(encoding="utf-8")).values()),
            "create_readback": create_readback,
            "update_before_sha256": before_sha,
            "update_readback": update_readback,
            "updated_exactly_once": True,
        }
        write_json(marker, result)
        return result
