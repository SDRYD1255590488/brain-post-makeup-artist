---
name: brain-post-makeup-artist
description: Plan the structure, compose, beautify, preview, audit, publish, update, and verify posts on the WorldQuant BRAIN Support forum, which is implemented on Zendesk Community, using platform-tested HTML components and guarded browser/API workflows. Use whenever a user asks to 发帖子、发布帖子、论坛排版、让长帖更好读、根据想法或素材写成论坛帖子、把笔记/Markdown/HTML/报告发到 BRAIN 论坛、更新已有论坛帖、上传帖子图片、测试论坛样式, or otherwise wants a polished and reliably published BRAIN forum post.
---

# BRAIN Post Makeup Artist

Turn rough content into readable forum HTML, then publish only through guarded, evidence-backed steps.

## Core workflow

1. Inspect the user's source and identify whether it is an idea, text, Markdown, HTML, or an existing post.
2. Choose an editing mode:
   - `preserve`: keep wording and structure; improve presentation only.
   - `polish`: improve hierarchy, headings, summaries, and readability. Use by default.
   - `develop`: add useful connective text or sections; tell the user what was added.
3. Read [references/compatibility.md](references/compatibility.md) before composing unfamiliar components. Read [references/platform-workflow.md](references/platform-workflow.md) before any platform access. Read [references/agent-guide.md](references/agent-guide.md) on first-time setup, when choosing among create/update/image paths, or when troubleshooting. Read [references/platform-architecture.md](references/platform-architecture.md) when explaining browser versus API behavior or adapting the integration.
4. Create or revise the Markdown source. When the post benefits from callouts, badges, KPI panels, timelines, figures, formulas, or foldouts, take the platform-tested markup from [assets/components.html](assets/components.html) and replace every placeholder. Never invent research results, metrics, quotations, or conclusions.
5. Run `compose`, then `audit`, then `preview`. Treat generated HTML as a draft until all three pass.
6. If the post contains local images, build and validate a manifest. Use `upload` only for drafting or explicit image-only work; use `publish-source` for the final retained-session publication.
7. Show the user the exact title, target topic, action, audit summary, and preview before a live write.
8. Perform `pure-api-publish`, `publish-source`, `publish`, or `update` only after explicit confirmation. Use `pure-api-publish` by default when no new local image must be registered. Use `publish-source` only when local images require the browser-authenticated editor workflow. Never retry a POST or PUT whose result is uncertain.
9. Confirm the immediate readback and report the post URL plus differences. Run standalone `verify` only when later or independent verification is needed.

Use the CLI through:

```bash
uv run python scripts/forum_skill.py <command> ...
```

Run `doctor --auth` first on a new machine. Add `--browser` only for a workflow that actually requires the browser. Run commands from this Skill directory.

When the local workspace already has a restricted `brain-mcp-v2` config, populate the ignored `.env` without exposing credentials:

```bash
uv run python scripts/configure_env.py
```

The script merges existing non-secret settings, writes `BRAIN_EMAIL/BRAIN_PASSWORD`, and enforces mode `0600` without printing either value.

If the default UV cache is not writable, set a task-scoped `UV_CACHE_DIR` outside the Skill.

For text-only publication or HTML that already contains permanent User Image paths, use `pure-api-publish`; it does not import or launch Playwright. When new local images must be registered, use `publish-source` instead of chaining `upload`, `publish`, and `verify`. For live acceptance, use the single `acceptance` command. The browser-backed commands keep one authenticated browser context across their consequential stages. The default `--browser-channel chromium` requires the version-matched bundled Chromium installed by `uv run python scripts/install_browser.py`; the installer and runtime share an ignored repository-local cache to avoid stale global revisions and locks. Use `auto` only when the user explicitly permits a system Chrome fallback; that preflight choice is not a retry.

`pure-api-publish` is a verified text-only publisher. Its HTTP-only SSO flow may end on a blocked Help Center HTML page, but the session API is the authoritative authentication check; do not reject an otherwise authenticated session merely because that final HTML response is 403.

Local image registration is different. The Zendesk editor uses the documented three-step User Images API, but current WorldQuant platform evidence shows that `/api/v2/guide/user_images/uploads` returns 401 when the session was established entirely by `requests`, even after matching editor headers, renewing the Zendesk session, and testing Chrome TLS/HTTP2 impersonation. The successful July workflow launched Chrome, opened the real editor, and used its file input; the editor then issued the upload-target POST, signed-storage PUT, and final User Image POST. Therefore use `upload` or `acceptance` for posts with local images. Do not describe this as end-to-end pure HTTP, and never accept pasted cookies as a workaround.

If Chrome exits with `SIGABRT` before navigation in a restricted sandbox, treat it as a local execution-permission failure, not a forum failure. Request browser execution outside the sandbox and make one fresh pre-dispatch launch. If an image workflow reaches a Cloudflare `Just a moment...` page before any upload dispatch, set `BRAIN_FORUM_HEADLESS=false` and make one visible-browser attempt. Never switch modes or retry after a consequential request may have been dispatched.

## Composition rules

The editing mode is an instruction to the Agent and provenance recorded by the deterministic renderer. The renderer structures supplied Markdown/HTML; it does not itself call a language model to rewrite prose. The Agent must make any `polish` or `develop` content edits before `compose` and disclose additions required by `develop`.

- Keep the platform post title outside the body; body headings start at `h2`.
- Prefer a concise opening summary, a named-anchor table of contents for long posts, and clear section boundaries.
- Use components for meaning: callouts for conclusions or risks, KPI panels for a few headline values, tables for comparison, timelines for sequence, and foldouts for optional detail.
- Use only verified tags and inline styles from `references/capabilities.json`. Do not use `<style>`, scripts, Grid, inline SVG, MathML, or external images.
- Use `<a name="..."></a>` for targets. Do not use ordinary `id` targets.
- Use MathJax LaTeX for roots, fractions, sums, or matrices. Use Unicode only for simple symbols.
- Keep color restrained. Use one theme consistently and preserve adequate text contrast.
- For existing HTML, preserve meaningful structure but normalize unsupported markup before publishing.

## Command contracts

### Compose

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md --title "Exact title" --mode polish \
  --theme emerald --output-dir .forum-runs/my-post
```

This writes `post-spec.json`, `post.md` or `source.html`, and `post.html`. Add `--image-map image-map.json` after image registration.

### Audit and preview

```bash
uv run python scripts/forum_skill.py audit \
  --html .forum-runs/my-post/post.html --strict
uv run python scripts/forum_skill.py preview \
  --html .forum-runs/my-post/post.html \
  --output-dir .forum-runs/my-post/preview
```

Do not waive strict audit errors for a formal post. Unknown capabilities require a probe or a stable fallback.

### Probe

Use `probe` only with an explicitly supplied editable AI_ONLY test post. It updates that one post and never creates a new probe automatically.

```bash
uv run python scripts/forum_skill.py probe \
  --post-id "$BRAIN_FORUM_PROBE_POST_ID" \
  --post-url "$BRAIN_FORUM_PROBE_POST_URL" \
  --html probe.html --confirm-post-id "$BRAIN_FORUM_PROBE_POST_ID" \
  --output-dir .forum-runs/probe --execute
```

After a successful probe, update the capability reference only when saved source and rendered-DOM readback support the conclusion.

### Publish and update

Resolve the topic every time. Do not rely on a committed personal default.

For a post without new local images, use the browserless publisher:

```bash
uv run python scripts/forum_skill.py pure-api-publish \
  --html post.html --title "Exact title" --confirm-title "Exact title" \
  --topic-id 123 --topic-name "Exact topic" \
  --output-dir .forum-runs/publish --strict --execute
```

When local images need registration, retain one authenticated browser session:

```bash
uv run python scripts/forum_skill.py publish-source \
  --input draft.md --title "Exact title" --confirm-title "Exact title" \
  --topic-id 123 --topic-name "Exact topic" \
  --manifest image-manifest.json --image-dir assets \
  --output-dir .forum-runs/publish --strict --execute
```

Omit `--manifest` and `--image-dir` together for a post without new local images. Use standalone `publish` when final audited HTML and all permanent image paths already exist.

```bash
uv run python scripts/forum_skill.py publish \
  --html post.html --title "Exact title" --confirm-title "Exact title" \
  --topic-id 123 --topic-name "Exact topic" \
  --output-dir .forum-runs/publish --strict --execute
```

```bash
uv run python scripts/forum_skill.py update \
  --post-id 123 --confirm-post-id 123 --post-url "https://..." \
  --html post.html --output-dir .forum-runs/update --strict --execute
```

The first update invocation is a read-only preflight and stops with the current source SHA-256. After showing the current source and differences to the user, repeat the command with `--confirm-current-sha256 <exact-sha256>`. This second invocation may perform the single PUT. Apply the same two-pass rule to `probe`.

## Safety invariants

- Load credentials from `.env`; never print or commit them.
- Persist only sanitized metadata and responses. Never retain cookies, CSRF tokens, JWTs, authorization headers, passwords, or signed upload URLs.
- Require `--execute` and exact confirmation values for every live write.
- Write an `operation_unknown.json` marker if a consequential request may have reached the server without a conclusive response. Block later writes until platform state is checked.
- Reject external images and temporary attachment URLs. Only publish `/hc/user_images/...` sources.
- Keep source HTML and rendered DOM as separate evidence.
- Do not copy historical toolkit `data/` into this Skill or public repositories.

## Live acceptance command

After exact authorization, run one retained acceptance post with one update:

```bash
uv run python scripts/forum_skill.py acceptance \
  --input acceptance.md \
  --title "[SKILL ACCEPTANCE] Exact title" \
  --confirm-title "[SKILL ACCEPTANCE] Exact title" \
  --topic-id 123 --topic-name "Exact AI_ONLY topic" \
  --manifest image-manifest.json --image-dir assets \
  --output-dir .forum-runs/acceptance --browser-channel chromium --execute
```

Do not run separate live commands in parallel with acceptance. A completed or unknown marker blocks reuse of the same output directory.

## References

- Read [references/agent-guide.md](references/agent-guide.md) for first-time configuration, workflow selection, command contracts, artifacts, and troubleshooting.
- Read [references/platform-architecture.md](references/platform-architecture.md) for the BRAIN/Support/Zendesk trust model, endpoint stability, status interpretation, and troubleshooting.
- Read [references/platform-workflow.md](references/platform-workflow.md) for authentication, images, create/update, and failure handling.
- Read [references/compatibility.md](references/compatibility.md) for component decisions and known sanitizer boundaries.
- Read [references/post-spec.md](references/post-spec.md) when producing or consuming `post-spec.json`.
- Read [references/acceptance.md](references/acceptance.md) before declaring the Skill stable or running live acceptance.
