# Compatibility guide

The machine-readable authority is `capabilities.json`. These conclusions came from saved platform HTML and rendered-page verification, not editor previews.

## Stable patterns

- Start the body at `h2`; the platform displays the title separately.
- Use `span` with inline `color`, not `font`.
- Use named anchors: `<a name="section-01"></a>` with `href="#section-01"`.
- Use bordered tables for comparisons and KPI groups.
- Use `div` or `aside` with background, border, and padding for callouts.
- Use `details`/`summary` for optional appendices.
- Use `figure`/`figcaption` and `/hc/user_images/...` for images.
- Use `\(...\)` or `\[...\]` for MathJax formulas.

## Known boundaries

- Rich-text paste can strip markup that a source/API write preserves.
- Ordinary `id` anchors, `font`, inline SVG, MathML, `progress`, and `meter` are rejected or degraded.
- External images and attachment-token URLs block reliable publication.
- CSS Grid, multi-column layouts, box shadow, margins, opacity, and smooth scrolling are not stable recommendations.
- Internal Zendesk endpoints and editor selectors may change. Run `doctor` and a probe after platform changes.

## Component selection

- Use a summary callout once near the top.
- Use at most four KPI cells in one row; prefer a normal table on narrow or text-heavy content.
- Use badges only for short status labels.
- Use timelines for ordered events, not general bullet lists.
- Keep warning colors local to warnings; do not color entire sections red or orange.
- Put implementation details, raw logs, and large code listings in foldouts.
