# Agent operator guide

Use this guide when configuring the Skill on a new machine, choosing a live-write
path, operating an existing post, or diagnosing a failed run. Read `SKILL.md` first;
its safety invariants override convenience.

## Contents

- [Operating contract](#operating-contract)
- [Initial configuration](#initial-configuration)
- [Select the workflow](#select-the-workflow)
- [Prepare and validate content](#prepare-and-validate-content)
- [Create without new local images](#create-without-new-local-images)
- [Create with local images](#create-with-local-images)
- [Update an existing post](#update-an-existing-post)
- [Add an image to an existing post](#add-an-image-to-an-existing-post)
- [Artifacts and completion criteria](#artifacts-and-completion-criteria)
- [Failure model](#failure-model)
- [Troubleshooting](#troubleshooting)
- [Security and public-repository hygiene](#security-and-public-repository-hygiene)

## Operating contract

Before acting, determine:

1. Is the task draft-only, create, update, probe, or verify?
2. Does it require registering a new local image?
3. What are the exact title, Topic ID, optional exact topic name, and—when
   updating—Post ID and canonical Support URL?
4. Has the user approved the exact live action and final content?

Never infer a personal default topic from repository history. Never convert an
update request into a create, or a failed create into an update, without new user
authorization.

Use a new output directory for each logical live run. A completed marker or unknown
marker makes that directory unsuitable for another write.

## Initial configuration

Run commands from the Skill root.

```bash
uv sync
```

Create `.env` without echoing secrets. On a BRAIN workspace with an existing local
`brain-mcp-v2` configuration, prefer:

```bash
uv run python scripts/configure_env.py
```

Otherwise create `.env` from `.env.example`. Required values are:

```dotenv
BRAIN_EMAIL=
BRAIN_PASSWORD=
```

Useful optional values:

```dotenv
BRAIN_API_URL=https://api.worldquantbrain.com
BRAIN_SUPPORT_URL=https://support.worldquantbrain.com
BRAIN_FORUM_LOCALE=en-us
BRAIN_FORUM_ARTIFACT_DIR=.forum-runs
BRAIN_FORUM_CHROME_CHANNEL=chromium
BRAIN_FORUM_HEADLESS=true
BRAIN_FORUM_PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers
```

Check mode `0600` on `.env`; do not print its content.

For a browserless create, run:

```bash
uv run python scripts/forum_skill.py doctor --auth
```

For local image registration or a browser-backed update, install the exact browser
revision and check the complete BRAIN → Support SSO → Zendesk CSRF chain:

```bash
uv run python scripts/install_browser.py
uv run python scripts/forum_skill.py doctor --auth --browser
```

In a managed environment with an approved system Chrome, set
`BRAIN_FORUM_CHROME_CHANNEL=chrome` before the first browser launch. Choose the
channel during preflight; do not use a failed post-dispatch launch as a fallback
probe.

## Select the workflow

| User intent | New local images? | Command path |
|---|---:|---|
| Draft only | Either | `compose` → `audit` → `preview`; stop |
| Create | No | `pure-api-publish` |
| Create | Yes | `publish-source` |
| Update | No | two-pass `update` |
| Update | Yes | `upload` → final `compose`/`audit` → two-pass `update` |
| Test unknown markup | No | two-pass `probe` on an authorized test post |
| Later readback | No | `verify` |

An existing permanent `/hc/user_images/...` URL is not a new local image. HTML that
already uses permanent paths can be sent through `pure-api-publish`.

## Prepare and validate content

Choose the editing mode before composition:

- `preserve`: keep wording and structure; change presentation only.
- `polish`: improve hierarchy and readability; default.
- `develop`: add useful connective material and disclose what was added.

The Agent performs prose editing. The renderer is deterministic and records the
selected mode; it does not call a language model.

Create the draft, then run:

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md \
  --title "EXACT_TITLE" \
  --mode polish \
  --theme emerald \
  --output-dir .forum-runs/draft

uv run python scripts/forum_skill.py audit \
  --html .forum-runs/draft/post.html \
  --title "EXACT_TITLE" \
  --strict \
  --output .forum-runs/draft/audit.json

uv run python scripts/forum_skill.py preview \
  --html .forum-runs/draft/post.html \
  --title "EXACT_TITLE" \
  --output-dir .forum-runs/draft/preview
```

`preview` writes local HTML only. Treat the post as unapproved until the user sees
the exact title, target, action, audit summary, and final body.

Strict publication requires `ok=true`, zero errors, and zero warnings. Do not waive
an unsupported component because it looks correct in a local browser.

## Create without new local images

Use the browserless HTTP path:

```bash
uv run python scripts/forum_skill.py pure-api-publish \
  --html .forum-runs/draft/post.html \
  --title "EXACT_TITLE" \
  --confirm-title "EXACT_TITLE" \
  --topic-id TOPIC_ID \
  --topic-name "EXACT_TOPIC_NAME" \
  --output-dir .forum-runs/create-run \
  --strict \
  --execute
```

The command resolves the topic, dispatches at most one create POST, saves the
identity immediately, and performs authenticated readback. A public Community
readback can return 404 while a pending post is available through the internal
authenticated endpoint; the command handles that fallback.

## Create with local images

Prepare a JSON manifest and keep every file below 2 MB:

```json
[
  {"key": "chart-one", "filename": "chart-one.png"}
]
```

Reference the filename from Markdown:

```markdown
![Descriptive alternative text](chart-one.png)
```

After local preview and explicit confirmation, use one retained browser session:

```bash
uv run python scripts/forum_skill.py publish-source \
  --input draft.md \
  --title "EXACT_TITLE" \
  --confirm-title "EXACT_TITLE" \
  --topic-id TOPIC_ID \
  --topic-name "EXACT_TOPIC_NAME" \
  --manifest image-manifest.json \
  --image-dir images \
  --output-dir .forum-runs/create-with-images \
  --strict \
  --execute
```

The command validates local paths before platform access, registers images,
re-composes with permanent paths, re-audits, dispatches one create, and reads back
without transferring session state between commands.

## Update an existing post

Bind the exact Post ID and canonical Support URL. The first invocation is deliberately
read-only even though `--execute` is present:

```bash
uv run python scripts/forum_skill.py update \
  --post-id POST_ID \
  --confirm-post-id POST_ID \
  --post-url "https://support.worldquantbrain.com/hc/en-us/community/posts/POST_ID-SLUG" \
  --html final.html \
  --output-dir .forum-runs/update-run \
  --strict \
  --execute
```

Expect it to stop with:

```text
read-only preflight complete; rerun with --confirm-current-sha256 CURRENT_SHA
```

Inspect `before-metadata.json` and `before-source.html`. Confirm exact Post ID,
title, topic, current content, and diff with the user. Then perform the only PUT:

```bash
uv run python scripts/forum_skill.py update \
  --post-id POST_ID \
  --confirm-post-id POST_ID \
  --confirm-current-sha256 CURRENT_SHA \
  --post-url "https://support.worldquantbrain.com/hc/en-us/community/posts/POST_ID-SLUG" \
  --html final.html \
  --output-dir .forum-runs/update-run \
  --strict \
  --execute
```

Never reuse an old SHA. A SHA mismatch means the platform changed after review; stop
and repeat the read-only review with the user.

## Add an image to an existing post

Do not use `publish-source`; it creates a new post. Register the image first without
a `--post-url`, which uses the new-post editor only as an image-registration surface:

```bash
uv run python scripts/forum_skill.py upload \
  --manifest image-manifest.json \
  --image-dir images \
  --mapping .forum-runs/image-update/image-map.json \
  --output-dir .forum-runs/image-update/upload \
  --execute
```

The mapping must contain only values beginning `/hc/user_images/`. Re-compose and
audit with it:

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md \
  --title "EXACT_EXISTING_TITLE" \
  --image-map .forum-runs/image-update/image-map.json \
  --output-dir .forum-runs/image-update/final

uv run python scripts/forum_skill.py audit \
  --html .forum-runs/image-update/final/post.html \
  --title "EXACT_EXISTING_TITLE" \
  --strict
```

Then use the two-pass update contract above. Image registration is a platform side
effect but does not create or update a community post.

## Artifacts and completion criteria

Keep runtime evidence under the ignored `.forum-runs/` directory.

| Artifact | Meaning |
|---|---|
| `post-spec.json` | source hash, editing mode, theme, structure, and image map |
| `post.html` | final local source intended for the platform |
| `audit.json` / `preflight.json` | compatibility and secret checks |
| `created-post.json` | conclusive create identity and readback |
| `before-metadata.json` | current update target and SHA |
| `update-response.json` | sanitized conclusive PUT response |
| `updated-post.json` | update identity and post-write readback |
| `image-map.json` | local key/filename to permanent User Image path |
| `operation_unknown.json` | a write may have reached the server; stop |
| `upload-unknown.json` | image registration may have completed; inspect before retry |

Create is complete when the command returns a numeric Post ID and valid Support URL,
writes `created-post.json`, and readback contains expected structure. Update is
complete when one PUT returns success and readback confirms the expected body. If
the platform displays the update but DOM readback times out, classify the post as
updated with verification pending; do not repeat the PUT.

## Failure model

Classify every failure before acting:

1. **Pre-dispatch:** validation, browser launch, topic lookup, selector, or audit
   failed before a consequential request. Fix the cause; a fresh attempt can be safe.
2. **Conclusive rejection:** the platform returned a complete non-success response.
   Diagnose the response; do not call it unknown or success.
3. **Unknown outcome:** a create/update/image registration may have reached the
   server without a conclusive identity or response. Stop, preserve the marker, and
   inspect platform state. Never retry automatically.

Authentication POSTs and signed image-byte PUTs are different from Community create
POSTs and post update PUTs. Report counts by operation, not only by HTTP verb.

## Troubleshooting

| Symptom | Interpretation | Action |
|---|---|---|
| `BRAIN authentication failed` | Credentials, access, or network failure | Check `.env` locally; do not print it |
| Final SSO HTML is 403, but session JSON is 200 with CSRF | HTTP-only session is usable | Continue text create; session JSON is authoritative |
| User Images upload-target returns 401 in pure HTTP | Tenant rejects HTTP-only image session | Use browser-editor image path; do not paste cookies |
| Browser executable missing | Playwright revision is not installed in the configured cache | Run `scripts/install_browser.py`; keep install/runtime paths identical |
| Chrome exits `SIGABRT` before navigation | Local sandbox/GUI permission failure | Obtain browser execution permission; retry only before dispatch |
| Page title is `Just a moment...` | Cloudflare replaced the editor in a headless session | If no upload was dispatched, set `BRAIN_FORUM_HEADLESS=false` for one visible attempt |
| Image input is not found | Editor DOM changed or Cloudflare page is active | Inspect page title first; do not repeatedly change selectors blindly |
| Public post readback is 404 after create | Pending visibility or public endpoint limitation | Check authenticated internal readback; do not create again |
| PUT returned 200 but rendered body timed out | Update is conclusive; visual verification is pending | Use read-only/API verification or user refresh; never repeat PUT |
| `operation_unknown.json` exists | Consequential write outcome is unknown | Search/read platform state by exact title/topic/Post ID before any new write |
| Image path is not `/hc/user_images/...` | Temporary or external asset | Reject it and do not publish |
| Strict audit has warnings | Conditional/unknown capability remains | Replace with a stable component or run an authorized probe |

The WorldQuant editor has been observed to allow a visible system Chrome session
when headless Chrome is challenged. Choose visible mode only before upload dispatch;
it is not a generic retry after an uncertain operation.

## Security and public-repository hygiene

- Never request or retain pasted cookies, CSRF tokens, JWTs, authorization headers,
  signed upload URLs, or copied `curl` commands containing session material.
- Never commit `.env`, `.forum-runs/`, `.playwright-browsers/`, `.venv/`, generated
  test images, page HTML evidence, or local database/cache files.
- Treat any exposed browser cookie/session bundle as compromised; instruct the user
  to log out and sign in again.
- Persist only sanitized responses and metadata.
- Validate every user-supplied post URL against HTTPS, the configured BRAIN Support
  host, and the confirmed Post ID.
- Resolve image paths inside the declared image directory; reject traversal,
  unsupported extensions, empty files, and files above 2 MB.
- Do not publish historical personal Topic IDs, Post IDs, credentials, or runtime
  evidence as reusable defaults.
