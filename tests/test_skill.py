from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit import audit_html  # noqa: E402
from common import Settings, browser_launch_kwargs, sanitize_data, sanitize_text, sha256_text  # noqa: E402
from configure_env import configure  # noqa: E402
from platform import acceptance_update_html, ensure_write_directory  # noqa: E402
from preview import wrapper  # noqa: E402
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

    def test_hash_is_stable(self) -> None:
        self.assertEqual(sha256_text("same"), sha256_text("same"))

    def test_preview_escapes_platform_title(self) -> None:
        rendered = wrapper("<p>Body</p>", '<img src=x onerror="alert(1)">')
        self.assertNotIn('<img src=x onerror="alert(1)">', rendered)
        self.assertIn("&lt;img", rendered)

    def test_bundled_chromium_does_not_set_system_channel(self) -> None:
        bundled = browser_launch_kwargs("chromium")
        system = browser_launch_kwargs("chrome")
        self.assertNotIn("channel", bundled)
        self.assertEqual(system["channel"], "chrome")

    def test_auto_browser_uses_bundled_when_present(self) -> None:
        executable = self.work / "chromium"
        executable.touch()
        self.assertNotIn("channel", browser_launch_kwargs("auto", executable))

    def test_auto_browser_falls_back_to_system_chrome_before_launch(self) -> None:
        launch = browser_launch_kwargs("auto", self.work / "missing-chromium")
        self.assertEqual(launch["channel"], "chrome")

    def test_explicit_missing_bundled_browser_has_actionable_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "playwright install chromium"):
            browser_launch_kwargs("chromium", self.work / "missing-chromium")

    def test_acceptance_update_component_is_strict_clean(self) -> None:
        updated = acceptance_update_html('<a name="post-top"></a><h2>Section</h2>')
        result = audit_html(updated)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["warnings"], [])
        self.assertIn("Update verification:", updated)


if __name__ == "__main__":
    unittest.main()
