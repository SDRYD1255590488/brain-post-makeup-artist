# Acceptance

Normal production publication is validated through the retained-session
`publish-source` path. The `acceptance` command adds a single controlled update to
that model and is intended for Skill release testing, not routine posting.

## Local gates

- `quick_validate.py` passes.
- Unit and CLI integration tests pass without network access.
- Strict audit reports zero errors and zero warnings for the representative long post.
- The generated local preview HTML contains the platform title and audited post body.
- Repository secret scan finds no credentials, cookies, JWTs, CSRF values, signed upload URLs, personal topic IDs, or personal post IDs.
- Re-running composition with the same source and options produces byte-identical HTML and post-spec content apart from output paths.

## Live acceptance

Run only after explicit user confirmation:

1. Resolve the configured `[AI_ONLY]` topic by ID and exact name.
2. Register one local PNG and confirm the result starts with `/hc/user_images/`.
3. Create one retained post whose title starts with `[SKILL ACCEPTANCE]` and whose body contains every stable component family.
4. Verify the saved source, rendered DOM, counts, navigation, MathJax, and image.
5. Update the same post exactly once with an additional verified callout; verify again.
6. Attempting the same create command again must be blocked by the local success marker.

Execute these steps through the single `acceptance` CLI command so they share one browser process and one authenticated context. Use the default `--browser-channel chromium` after installing the version-matched browser with `uv run python scripts/install_browser.py`. Use `auto` only when a user explicitly permits a system Chrome fallback. Do not probe by launching one browser and then retrying with another. Do not assemble the live acceptance from separate browser-launching commands.

A pre-navigation `SIGABRT` inside a restricted sandbox is an execution-permission failure. Obtain browser execution permission and make one new pre-dispatch launch. A missing bundled executable is a dependency/configuration failure; either install the matching Playwright browser or explicitly use an installed system Chrome.

Do not create multiple acceptance posts. If a write result is uncertain, stop and inspect platform state.
