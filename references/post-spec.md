# Post specification

`post-spec.json` is the reproducible composition contract.

```json
{
  "schema_version": 1,
  "title": "Exact platform title",
  "source": {"path": "draft.md", "type": "markdown", "sha256": "..."},
  "editing": {"mode": "polish"},
  "theme": {"name": "emerald"},
  "structure": {
    "navigation": true,
    "body_heading_start": 2,
    "sections": [{"anchor": "section-01", "title": "核心结论"}]
  },
  "assets": {"image_map": null, "images": []},
  "output": {"html": "post.html"}
}
```

Rules:

- `schema_version` is `1`.
- `title` is the platform title and must not be repeated as an `h1` in the body.
- `source.type` is `text`, `markdown`, or `html`.
- `editing.mode` is `preserve`, `polish`, or `develop`.
- `theme.name` is `emerald`, `indigo`, `coral`, or a key added to `assets/themes.json`.
- `assets.images` contains only local filenames and final `/hc/user_images/...` mappings; never store signed upload URLs.
- Destination topic and post IDs belong to the confirmation step and are not embedded in reusable public examples.
