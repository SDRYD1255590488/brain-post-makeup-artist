from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit import audit_html  # noqa: E402
from common import Settings, browser_launch_kwargs, ensure_no_unknown_operation, sanitize_data, sanitize_text, sha256_text, write_operation_unknown  # noqa: E402
from configure_env import configure  # noqa: E402
from forum_skill import doctor  # noqa: E402
from platform import ForumBrowser, acceptance_update_html, ensure_write_directory, publish_source, resolve_manifest_image, validate_community_post_url  # noqa: E402
from preview import create_preview, wrapper  # noqa: E402
from pure_api import establish_support_session  # noqa: E402
from render import compose  # noqa: E402


class SkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_compose_removes_body_h1_and_adds_navigation(self) -> None:
        source = self.work / "draft.md"
        source.write_text("# Platform title\n\nLead.\n\n## One\n\nA.\n\n## Two\n\nB.\n", encoding="utf-8")
        spec = compose(source, "Platform title", self.work / "out")
        html = (self.work / "out" / "post.html").read_text(encoding="utf-8")
        self.assertNotIn("<h1", html)
        self.assertIn('name="post-top"', html)
        self.assertEqual(len(spec["structure"]["sections"]), 2)

    def test_compose_is_deterministic(self) -> None:
        source = self.work / "draft.md"
        source.write_text("## One\n\nText\n\n## Two\n\nText\n", encoding="utf-8")
        compose(source, "Title", self.work / "a", theme_name="indigo")
        compose(source, "Title", self.work / "b", theme_name="indigo")
        self.assertEqual((self.work / "a" / "post.html").read_bytes(), (self.work / "b" / "post.html").read_bytes())
        a = json.loads((self.work / "a" / "post-spec.json").read_text())
        b = json.loads((self.work / "b" / "post-spec.json").read_text())
        self.assertEqual(a, b)

    def test_fenced_code_class_is_normalized(self) -> None:
        source = self.work / "draft.md"
        source.write_text("## Code\n\n```html\n<p>x</p>\n```\n", encoding="utf-8")
        compose(source, "Title", self.work / "out")
        html = (self.work / "out" / "post.html").read_text(encoding="utf-8")
        self.assertNotIn("class=", html)
        self.assertTrue(audit_html(html)["ok"])

    def test_image_requires_registered_mapping(self) -> None:
        source = self.work / "draft.md"
        source.write_text("## Chart\n\n![Chart](chart.png)\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "missing registered"):
            compose(source, "Title", self.work / "out")

    def test_registered_image_is_rendered_as_figure(self) -> None:
        source = self.work / "draft.md"
        source.write_text("## Chart\n\n![Chart](chart.png)\n", encoding="utf-8")
        mapping = self.work / "map.json"
        mapping.write_text(json.dumps({"chart.png": "/hc/user_images/abc.png"}), encoding="utf-8")
        compose(source, "Title", self.work / "out", image_map_path=mapping)
        html = (self.work / "out" / "post.html").read_text(encoding="utf-8")
        self.assertIn("<figure", html)
        self.assertIn('/hc/user_images/abc.png', html)
        self.assertTrue(audit_html(html)["ok"])

    def test_component_library_uses_only_stable_capabilities(self) -> None:
        html = (ROOT / "assets" / "components.html").read_text(encoding="utf-8")
        html = html.replace("/hc/user_images/REPLACE_ME.png", "/hc/user_images/example.png")
        result = audit_html(html)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["warnings"], [])

    def test_audit_rejects_external_images_and_ids(self) -> None:
        result = audit_html('<h2 id="x">X</h2><img src="https://example.com/a.png">')
        self.assertFalse(result["ok"])
        self.assertTrue(result["invalid_images"])
        self.assertTrue(result["id_attributes"])

    def test_audit_rejects_missing_anchor_target(self) -> None:
        result = audit_html('<p><a href="#missing">Go</a></p>')
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_anchor_targets"], ["missing"])

    def test_audit_detects_secrets_and_placeholders(self) -> None:
        html = '<p>me@example.com password=hunter2 REPLACE_ME</p>'
        result = audit_html(html)
        self.assertFalse(result["ok"])
        self.assertIn("email address", result["secret_findings"])

    def test_sanitizer_redacts_nested_sensitive_values(self) -> None:
        signed_key = "X-Amz-" + "Signature"
        payload = {"csrf_token": "secret", "author_id": 42, "nested": {"url": f"https://x.test/a?{signed_key}=abc"}}
        clean = sanitize_data(payload)
        self.assertEqual(clean["csrf_token"], "[REDACTED]")
        self.assertEqual(clean["author_id"], "[REDACTED]")
        self.assertIn("REDACTED", clean["nested"]["url"])

    def test_sanitize_text_redacts_email_and_jwt(self) -> None:
        value = "me@example.com " + ".".join(["eyJabcdefgh", "abcdefgh", "abcdefgh"])
        clean = sanitize_text(value)
        self.assertNotIn("me@example.com", clean)
        self.assertIn("REDACTED", clean)

    def test_settings_load_local_env_without_echoing(self) -> None:
        env = self.work / ".env"
        env.write_text("BRAIN_" + "EMAIL=user@example.com\n" + "BRAIN_" + "PASSWORD=secret\n", encoding="utf-8")
        settings = Settings.from_env(env)
        self.assertEqual(settings.email, "user@example.com")
        self.assertEqual(settings.password, "secret")
        self.assertEqual(settings.chrome_channel, "chromium")

    def test_default_browser_channel_is_version_matched_chromium(self) -> None:
        settings = Settings.from_env(self.work / "missing.env", require_credentials=False)
        self.assertEqual(settings.chrome_channel, "chromium")

    def test_secure_config_import_writes_mode_0600(self) -> None:
        config = self.work / "config.json"
        target = self.work / ".env"
        config.write_text(json.dumps({"credentials": {"email": "user@example.com", "password": "secret"}}), encoding="utf-8")
        result = configure(config, target)
        self.assertEqual(result["mode"], "0o600")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("secret", json.dumps(result))

    def test_unknown_operation_marker_blocks_write(self) -> None:
        output = self.work / "run"
        output.mkdir()
        (output / "operation_unknown.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "unknown"):
            ensure_write_directory(output)

    def test_legacy_unknown_operation_marker_also_blocks_write(self) -> None:
        output = self.work / "run"
        output.mkdir()
        (output / "operation-unknown.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "unknown"):
            ensure_no_unknown_operation(output)

    def test_unknown_operation_writer_uses_canonical_name(self) -> None:
        marker = write_operation_unknown(self.work / "run", {"operation": "create"})
        self.assertEqual(marker.name, "operation_unknown.json")
        self.assertTrue(marker.is_file())

    def test_post_url_is_bound_to_support_host_and_post_id(self) -> None:
        settings = Settings.from_env(self.work / "missing.env", require_credentials=False)
        valid = "https://support.worldquantbrain.com/hc/en-us/community/posts/12345-title"
        self.assertEqual(validate_community_post_url(settings, valid, post_id="12345"), valid)
        with self.assertRaisesRegex(RuntimeError, "Post ID"):
            validate_community_post_url(settings, valid, post_id="999")
        with self.assertRaisesRegex(RuntimeError, "Support host"):
            validate_community_post_url(settings, "https://example.com/hc/en-us/community/posts/12345-title")

    def test_manifest_image_cannot_escape_image_directory(self) -> None:
        image_dir = self.work / "images"
        image_dir.mkdir()
        (image_dir / "ok.png").write_bytes(b"png")
        outside = self.work / "outside.png"
        outside.write_bytes(b"png")
        self.assertEqual(resolve_manifest_image(image_dir, "ok.png"), (image_dir / "ok.png").resolve())
        with self.assertRaisesRegex(RuntimeError, "escapes"):
            resolve_manifest_image(image_dir, "../outside.png")

    def test_forum_browser_cleans_up_when_launch_fails(self) -> None:
        executable = self.work / "chromium"
        executable.touch()

        class FakeSession:
            cookies: list[object] = []

            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        class FakeChromium:
            executable_path = str(executable)

            async def launch(self, **kwargs: object) -> None:
                raise RuntimeError("launch failed")

        class FakePlaywright:
            def __init__(self) -> None:
                self.chromium = FakeChromium()
                self.stopped = False

            async def stop(self) -> None:
                self.stopped = True

        class FakeStarter:
            def __init__(self, playwright: FakePlaywright) -> None:
                self.playwright = playwright

            async def start(self) -> FakePlaywright:
                return self.playwright

        session = FakeSession()
        playwright = FakePlaywright()
        settings = Settings.from_env(self.work / "missing.env", require_credentials=False)
        with patch("platform.authenticate_brain", return_value=session), patch("platform.async_playwright", return_value=FakeStarter(playwright)):
            with self.assertRaisesRegex(RuntimeError, "launch failed"):
                asyncio.run(ForumBrowser(settings).__aenter__())
        self.assertTrue(session.closed)
        self.assertTrue(playwright.stopped)

    def test_combined_doctor_checks_support_csrf_in_same_browser_context(self) -> None:
        settings = Settings.from_env(self.work / "missing.env", require_credentials=False)

        class FakeForumBrowser:
            def __init__(self, supplied: Settings) -> None:
                self.settings = supplied

            async def __aenter__(self) -> "FakeForumBrowser":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def csrf(self) -> str:
                return "not-emitted"

        with patch("forum_skill.Settings.from_env", return_value=settings), patch("platform.ForumBrowser", FakeForumBrowser):
            result = asyncio.run(doctor(SimpleNamespace(auth=True, browser=True)))
        self.assertEqual(result["authentication"], "ok")
        self.assertEqual(result["support_session"], "ok")
        self.assertNotIn("not-emitted", json.dumps(result))

    def test_publish_source_fails_local_preflight_before_authentication(self) -> None:
        source = self.work / "draft.md"
        source.write_text("## Chart\n\n![Missing](missing.png)\n", encoding="utf-8")
        with patch("platform.Settings.from_env") as settings_loader:
            with self.assertRaisesRegex(RuntimeError, "missing registered"):
                asyncio.run(publish_source(
                    source,
                    "Title",
                    "Title",
                    1,
                    "Topic",
                    self.work / "run",
                    mode="polish",
                    theme="emerald",
                    browser_channel="chromium",
                    strict=True,
                ))
        settings_loader.assert_not_called()

    def test_cli_publish_is_dry_run_by_default(self) -> None:
        html = self.work / "post.html"
        html.write_text("<h2>Safe</h2>", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "forum_skill.py"), "publish", "--html", str(html), "--title", "T", "--confirm-title", "T", "--topic-id", "1", "--output-dir", str(self.work / "publish")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--execute", result.stderr)

    def test_pure_api_cli_does_not_import_playwright(self) -> None:
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(SCRIPTS)!r}); "
            "import forum_skill; "
            "print('playwright' in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), "False")

    def test_pure_api_accepts_blocked_final_html_when_session_is_authenticated(self) -> None:
        class FakeResponse:
            def __init__(self, status: int, url: str, *, location: str = "", payload: dict | None = None):
                self.status_code = status
                self.url = url
                self.headers = {"Location": location} if location else {}
                self._payload = payload or {}

            def json(self) -> dict:
                return self._payload

        class FakeSession:
            def __init__(self) -> None:
                self.headers: dict[str, str] = {}
                self.redirects = [
                    FakeResponse(302, "https://api.worldquantbrain.com/authentication/support", location="https://worldquantbrain.zendesk.com/access/jwt?token=redacted"),
                    FakeResponse(302, "https://worldquantbrain.zendesk.com/access/jwt?token=redacted", location="https://support.worldquantbrain.com/hc/en-us/community/topics"),
                    FakeResponse(403, "https://support.worldquantbrain.com/hc/en-us/community/topics"),
                ]

            def get(self, url: str, **kwargs: object) -> FakeResponse:
                if url.endswith("/api/v2/help_center/sessions.json"):
                    return FakeResponse(200, url, payload={"current_session": {"csrf_token": "csrf"}})
                return self.redirects.pop(0)

        settings = Settings(
            email="user@example.com",
            password="secret",
            brain_api_url="https://api.worldquantbrain.com",
            support_url="https://support.worldquantbrain.com",
            locale="en-us",
            artifact_dir=self.work,
            chrome_channel="chromium",
        )
        fake = FakeSession()
        with patch("pure_api.authenticate_brain", return_value=fake) as authenticate:
            session, csrf = establish_support_session(settings)
        authenticate.assert_called_once_with(settings, trust_env=False)
        self.assertIs(session, fake)
        self.assertEqual(csrf, "csrf")
        self.assertEqual(fake.redirects, [])

    def test_hash_is_stable(self) -> None:
        self.assertEqual(sha256_text("same"), sha256_text("same"))

    def test_preview_escapes_platform_title(self) -> None:
        rendered = wrapper("<p>Body</p>", '<img src=x onerror="alert(1)">')
        self.assertNotIn('<img src=x onerror="alert(1)">', rendered)
        self.assertIn("&lt;img", rendered)

    def test_preview_writes_only_html_artifacts(self) -> None:
        html = self.work / "post.html"
        html.write_text("<h2>Body</h2>", encoding="utf-8")
        result = asyncio.run(create_preview(html, self.work / "preview", "Title"))
        self.assertEqual(set(result), {"rendered_html"})
        self.assertTrue((self.work / "preview" / "rendered.html").is_file())
        self.assertEqual(list((self.work / "preview").glob("*.png")), [])

    def test_preview_module_does_not_import_playwright(self) -> None:
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(SCRIPTS)!r}); "
            "import preview; "
            "print('playwright' in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), "False")

    def test_bundled_chromium_does_not_set_system_channel(self) -> None:
        bundled = browser_launch_kwargs("chromium")
        system = browser_launch_kwargs("chrome")
        self.assertNotIn("channel", bundled)
        self.assertEqual(system["channel"], "chrome")

    def test_browser_headless_mode_is_explicit(self) -> None:
        self.assertTrue(browser_launch_kwargs("chrome")["headless"])
        self.assertFalse(browser_launch_kwargs("chrome", headless=False)["headless"])

    def test_auto_browser_uses_bundled_when_present(self) -> None:
        executable = self.work / "chromium"
        executable.touch()
        self.assertNotIn("channel", browser_launch_kwargs("auto", executable))

    def test_auto_browser_falls_back_to_system_chrome_before_launch(self) -> None:
        launch = browser_launch_kwargs("auto", self.work / "missing-chromium")
        self.assertEqual(launch["channel"], "chrome")

    def test_explicit_missing_bundled_browser_has_actionable_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "install_browser.py"):
            browser_launch_kwargs("chromium", self.work / "missing-chromium")

    def test_acceptance_update_component_is_strict_clean(self) -> None:
        updated = acceptance_update_html('<a name="post-top"></a><h2>Section</h2>')
        result = audit_html(updated)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["warnings"], [])
        self.assertIn("Update verification:", updated)


if __name__ == "__main__":
    unittest.main()
