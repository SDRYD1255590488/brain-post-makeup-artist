# WorldQuant BRAIN Support platform architecture

This reference explains why the Skill uses both HTTP APIs and a browser-authenticated
session. Read it when diagnosing authentication, 401/403 responses, image uploads,
or adapting the workflow. It describes the WorldQuant deployment of Zendesk; it is
not a generic guarantee for every Zendesk tenant.

## Contents

- [System boundary](#system-boundary)
- [Authentication and session handoff](#authentication-and-session-handoff)
- [Text and HTML publishing](#text-and-html-publishing)
- [Local image registration](#local-image-registration)
- [API stability](#api-stability)
- [Failure semantics](#failure-semantics)
- [Troubleshooting](#troubleshooting)
- [Security rules](#security-rules)
- [Evidence and official references](#evidence-and-official-references)

## System boundary

Five actors participate in a live publication:

1. **BRAIN authentication** validates the user's BRAIN credentials and creates a
   BRAIN session.
2. **BRAIN Support SSO** exchanges that session for access to the Support site.
3. **Zendesk Help Center / Community** owns topics, posts, the editor session, CSRF
   protection, and readback APIs.
4. **Zendesk User Images and signed object storage** register local images and move
   their bytes to temporary storage before returning a permanent User Image path.
5. **This Skill** composes and audits HTML locally, orchestrates the authenticated
   calls, guards writes, and saves sanitized evidence.

The important boundary is that a valid BRAIN session is not automatically a valid
Zendesk editor session. The SSO exchange must complete, Zendesk cookies must remain
in the same client context, and a current CSRF token must be obtained from that
context.

```text
BRAIN credentials
      |
      v
BRAIN authentication session
      |
      v
/authentication/support SSO handoff
      |
      v
Zendesk Support cookies + /api/v2/help_center/sessions.json CSRF
      |
      +--> Community API create/readback
      |
      +--> editor-mediated User Images workflow
```

Composition, audit, and local preview happen before this chain and need no account.

## Authentication and session handoff

The browser-backed path authenticates against BRAIN, copies only the resulting BRAIN
cookies into one new Playwright context, opens the Support SSO endpoint, and then
requests `/api/v2/help_center/sessions.json` inside the resulting Support origin. A
non-empty `current_session.csrf_token` is the end-to-end readiness check.

The pure HTTP text path manually follows the same SSO redirects. Cloudflare can
return 403 for the final human-facing HTML page even when the Zendesk session was
created successfully. For that path, the session JSON endpoint—not the final HTML
status—is authoritative. A 200 session response with a CSRF token means the text
publishing session is usable.

Do not copy cookies between unrelated runs, mix cookies and CSRF values from
different sessions, or treat a successful BRAIN login alone as Support readiness.
`doctor --auth --browser` deliberately exercises the complete browser SSO and CSRF
chain.

## Text and HTML publishing

The platform editor is a rich-text editor, not a raw HTML paste surface. Pasting
HTML with Ctrl-C/Ctrl-V normally transfers rendered clipboard content, and the
editor or browser may normalize it before submission. Direct-source publishing
sends the audited HTML string as the post `details`, so supported inline styles and
semantic components reach Zendesk's server-side sanitizer more faithfully.

The public create path used here is:

```text
POST /api/v2/community/posts.json
```

It is a same-origin API request with the current Zendesk cookies and CSRF token.
After a successful create, the Skill immediately opens the returned post URL,
retrieves the stored source, captures rendered DOM and visible text, and compares
structural counts. A permanent `created-post.json` marker prevents duplicate reuse
of the same run directory.

Text-only posts can use `pure-api-publish`. Posts containing already registered
`/hc/user_images/...` paths are also text at this stage; no new upload is needed.

## Local image registration

The editor uses Zendesk's documented User Images protocol:

```text
POST /api/v2/guide/user_images/uploads   request an upload target
PUT  <signed object-storage URL>         upload the bytes
POST /api/v2/guide/user_images           register the User Image
```

Only the final path beginning `/hc/user_images/` is safe to place in a post. Signed
storage URLs and request-upload attachment URLs are temporary and must never be
published or persisted.

On the WorldQuant tenant, sessions created entirely by ordinary HTTP clients have
successfully created text posts but returned 401 at the first User Images call.
Matching editor headers, renewing the Zendesk session, anonymous calls, and Chrome
TLS/HTTP2 impersonation did not remove that boundary. The verified image workflow
opens the real Zendesk editor in a browser-authenticated context and selects the
local file; the editor then performs the three API calls above.

This is still API-based byte transfer, but it is **not** an end-to-end browserless
workflow. `publish-source` intentionally keeps the same browser context for editor
image registration, final compose, one create request, and readback. This removes
the most common cookie/CSRF state-transfer failure.

## API stability

Treat integrations in three classes:

- **Public Zendesk APIs:** Community create/read endpoints and documented User
  Images endpoints. Prefer these when the tenant permits the operation.
- **Browser-internal endpoints:** for example
  `/hc/api/internal/communities/posts/{id}`, needed for some pending-post updates
  that the public API cannot read. These are not a stable public contract and must
  remain isolated behind readback and exact-ID guards.
- **Editor selectors and UI behavior:** file inputs, dialogs, and menu labels can
  change without API notice. A missing selector is a compatibility failure, not
  permission to invent a different write path.

Platform HTML capability results are evidence, not universal Zendesk guarantees.
Use `capabilities.json` and probe unknown markup only on an explicitly authorized
editable test post.

## Failure semantics

Classify a failure before deciding whether any retry is safe:

- **Pre-dispatch:** validation, browser launch, topic lookup, audit, or selector
  failure occurred before a consequential request. Fix the cause and start a fresh
  run directory.
- **Conclusive rejection:** the server returned a complete non-success response.
  Record the sanitized response and diagnose it. Do not disguise it as success.
- **Operation unknown:** a POST/PUT may have reached the server, but the response was
  lost, timed out, or lacked identity. Write `operation_unknown.json`, stop, and
  inspect platform state by title/topic/Post ID before considering another write.

The Skill recognizes the earlier legacy filename `operation-unknown.json` too, so a
run cannot bypass the guard by switching transports.

Useful status interpretations are contextual:

- `401`: the current Zendesk session is not accepted for that endpoint; BRAIN login
  success does not disprove this.
- `403`: the request was blocked or forbidden. A final SSO landing-page 403 can be
  harmless only when the session JSON endpoint independently returns 200 + CSRF.
- `404`: wrong target, insufficient visibility, or a public API that cannot expose a
  pending post. Never infer deletion without a second authoritative check.
- `429`: rate limited; do not retry a possibly dispatched create/update blindly.
- `5xx`, timeout, or disconnect after dispatch: outcome may be unknown.

## Troubleshooting

Use this order so each check proves the prerequisite for the next one:

1. Run local compose and strict audit. Fix deterministic input errors first.
2. For text-only publication, run `doctor --auth` and use `pure-api-publish`; no
   browser preflight is needed. If BRAIN auth fails, verify `.env` locally without
   printing it.
3. Only for local images or a browser-backed update, run `doctor --auth --browser`.
   If browser launch fails, run `uv run python scripts/install_browser.py` to install
   the locked revision, or explicitly select permitted system Chrome.
4. If the browser-backed Support session/CSRF check fails, diagnose the SSO handoff;
   do not paste cookies.
5. Resolve the exact topic ID and optional exact topic name.
6. For local images, validate every manifest path and file before opening the
   editor. A 401 at the upload-target endpoint means the session is not accepted for
   image registration; use the retained browser-editor path. If a headless editor
   is replaced by Cloudflare's `Just a moment...` page before any upload request,
   make one visible-browser attempt with `BRAIN_FORUM_HEADLESS=false`.
7. After user confirmation, use one `pure-api-publish` run for text/registered-image
   HTML, or one `publish-source` run when local images require registration. If an
   unknown marker is written, stop and search/read before any retry.
8. Treat successful create plus failed readback as “created, verification pending,”
   never as a failed create eligible for repetition.

## Security rules

- Store credentials only in ignored `.env` files with mode `0600`.
- Never ask users to paste cookies, CSRF tokens, JWTs, signed upload URLs, or full
  copied browser requests. If exposed, advise session revocation/re-login.
- Keep transient authentication values in memory only.
- Sanitize saved responses and metadata; never archive browser storage state.
- Validate post URLs against the configured Support host and exact Post ID.
- Resolve image paths inside the declared image directory and reject traversal,
  unsupported extensions, empty files, and files over the platform limit.

## Evidence and official references

- Component and image workflow evidence: 2026-07-25 retained browser/editor run.
- Pure HTTP text publication: live verified 2026-08-18.
- HTTP-only User Images boundary: reproduced 2026-08-18 to 2026-08-19.
- [Zendesk Help Center API introduction](https://developer.zendesk.com/api-reference/help_center/help-center-api/introduction/)
- [Zendesk User Images API](https://developer.zendesk.com/api-reference/help_center/help-center-api/user_images/)

Re-verify tenant-specific behavior when Zendesk, Cloudflare, BRAIN SSO, Playwright,
or the editor changes. Do not convert observations into credentials or hard-coded
personal defaults.
