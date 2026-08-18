# Platform workflow

## Authentication

1. Read `.env` without printing values.
2. POST Basic Auth to `${BRAIN_API_URL}/authentication`.
3. Immediately GET the same endpoint to verify the authenticated session.
4. Inject only the resulting cookies into a fresh Playwright context.
5. Navigate to `${BRAIN_API_URL}/authentication/support`, then the support site.
6. Fetch `/api/v2/help_center/sessions.json` inside the page to obtain the current CSRF token. Keep it in memory only.

The browser is the Support SSO session exchanger; create/update remain same-origin API calls. HTTP-only Support SSO is not the default because ordinary clients may receive Cloudflare/Zendesk 403 before forum topic lookup. Use one browser context per live workflow and close it after readback.

Browser selection is a preflight decision. The default `chromium` requires the Playwright bundled executable installed by `uv run playwright install chromium`; this pins the browser revision to the Python package. `auto` is an explicit compatibility option: it uses the bundled executable when installed and otherwise selects system Chrome. If a restricted sandbox aborts Chrome before navigation, obtain browser execution permission and restart only while no consequential request has been dispatched.

## Images

Use the real new-post or edit-dialog file input. The editor performs:

1. request an upload target;
2. upload bytes to temporary storage;
3. register a Zendesk User Image.

Accept only the final `/hc/user_images/...` path. Do not persist signed upload targets and do not treat `/hc/request_uploads` attachment-token URLs as final images.

Upload sequentially, save the final mapping after every image, and pause between images. A failed image registration may be retried only when the response proves registration did not complete.

## Create

- Resolve `topic_id` and optional exact topic name immediately before the write.
- Audit the final HTML and save a sanitized source snapshot.
- Perform exactly one `POST /api/v2/community/posts.json`.
- On a clear non-success response, record the sanitized failure.
- On timeout, disconnect, or malformed response after dispatch, write `operation_unknown.json` and stop. Search the topic/title before any later attempt.
- On success, navigate to the returned URL and save separate source/readback HTML, visible text, metadata, and screenshot.

## Update and probe

- Fix the target by exact Post ID and URL.
- Read and save the current post before writing.
- Pending posts may require `/hc/api/internal/communities/posts/{post_id}` because the public Community API can return 404.
- Preserve the existing title and topic unless the user explicitly requests a change.
- Perform exactly one PUT, then reload and verify.
- A probe uses this update path against one explicitly configured AI_ONLY post; never create a probe implicitly.

## Verification

Compare at least title, topic, visible-text hash, body byte length, headings, images, tables, named anchors, and hash links. Count equality is necessary but not sufficient: retain a full-page screenshot for visual review.
