#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mistune
from bs4 import BeautifulSoup, Tag

from common import SKILL_ROOT, sha256_text, write_json, write_text


THEMES_PATH = SKILL_ROOT / "assets" / "themes.json"


def load_themes() -> dict[str, dict[str, str]]:
    return json.loads(THEMES_PATH.read_text(encoding="utf-8"))


def detect_type(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if path.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    if path.suffix.lower() in {".html", ".htm"}:
        return "html"
    return "text"


def markdown_to_soup(source: str) -> BeautifulSoup:
    markdown = mistune.create_markdown(plugins=["table", "strikethrough"])
    return BeautifulSoup(markdown(source), "html.parser")


def text_to_markdown(source: str) -> str:
    paragraphs = [part.strip() for part in source.replace("\r\n", "\n").split("\n\n") if part.strip()]
    return "\n\n".join(paragraphs) + ("\n" if paragraphs else "")


def set_style(tag: Tag, declarations: str) -> None:
    existing = str(tag.get("style") or "").strip().rstrip(";")
    tag["style"] = f"{existing}; {declarations}".strip("; ") + ";"


def wrap_color(soup: BeautifulSoup, tag: Tag, color: str) -> None:
    wrapper = soup.new_tag("span")
    wrapper["style"] = f"color: {color};"
    for child in list(tag.contents):
        wrapper.append(child.extract())
    tag.append(wrapper)


def normalize_headings(soup: BeautifulSoup, title: str) -> None:
    first_h1 = soup.find("h1")
    if first_h1:
        if first_h1.get_text(" ", strip=True) == title.strip() or first_h1 is soup.find(True):
            first_h1.decompose()
        else:
            first_h1.name = "h2"
    for heading in soup.find_all("h1"):
        heading.name = "h2"
    for tag in soup.find_all(True):
        tag.attrs.pop("class", None)


def replace_images(soup: BeautifulSoup, image_map: dict[str, str]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for image in list(soup.find_all("img")):
        original = str(image.get("src") or "")
        filename = Path(original).name
        mapped = str(image_map.get(original) or image_map.get(filename) or "")
        if not mapped.startswith("/hc/user_images/"):
            raise RuntimeError(f"missing registered /hc/user_images mapping for {filename or original}")
        alt = str(image.get("alt") or filename or "Image")
        figure = soup.new_tag("figure")
        set_style(figure, "text-align: center")
        rendered = soup.new_tag("img")
        rendered["src"] = mapped
        rendered["alt"] = alt
        rendered["style"] = "width: 100%; max-width: 100%; height: auto;"
        caption = soup.new_tag("figcaption")
        caption["style"] = "color: #5F554B; text-align: center;"
        caption.string = alt
        figure.extend([rendered, caption])
        parent = image.parent
        if parent and parent.name == "p" and len(parent.find_all(True, recursive=False)) == 1:
            parent.replace_with(figure)
        else:
            image.replace_with(figure)
        images.append({"filename": filename, "path": mapped, "alt": alt})
    return images


def add_navigation(soup: BeautifulSoup, theme: dict[str, str]) -> list[dict[str, str]]:
    headings = list(soup.find_all("h2"))
    sections: list[dict[str, str]] = []
    top = soup.new_tag("a")
    top["name"] = "post-top"
    if soup.contents:
        soup.insert(0, top)
    else:
        soup.append(top)
    for index, heading in enumerate(headings, start=1):
        anchor_name = f"section-{index:02d}"
        anchor = soup.new_tag("a")
        anchor["name"] = anchor_name
        heading.insert_before(anchor)
        sections.append({"anchor": anchor_name, "title": heading.get_text(" ", strip=True)})
    if len(sections) >= 2:
        nav = soup.new_tag("div")
        nav["style"] = (
            f"background-color: {theme['surface']}; border-left: 4px solid {theme['heading']}; "
            "padding: 12px;"
        )
        label = soup.new_tag("strong")
        label.string = "目录"
        nav.append(label)
        for section in sections:
            paragraph = soup.new_tag("p")
            link = soup.new_tag("a", href=f"#{section['anchor']}")
            link.string = section["title"]
            paragraph.append(link)
            nav.append(paragraph)
        top.insert_after(nav)
        for heading in headings[1:]:
            back = soup.new_tag("p")
            link = soup.new_tag("a", href="#post-top")
            link.string = "返回顶部"
            back.append(link)
            heading.find_previous("a", attrs={"name": True}).insert_before(back)
        footer = soup.new_tag("p")
        footer_link = soup.new_tag("a", href="#post-top")
        footer_link.string = "返回顶部"
        footer.append(footer_link)
        soup.append(footer)
    return sections


def apply_styles(soup: BeautifulSoup, theme: dict[str, str]) -> None:
    for name, color in (("h2", theme["heading"]), ("h3", theme["subheading"]), ("h4", theme["subheading"])):
        for heading in soup.find_all(name):
            wrap_color(soup, heading, color)
            if name == "h2":
                set_style(heading, f"border-bottom: 1px solid {theme['border']}; padding: 8px")
            elif name == "h3":
                set_style(heading, f"border-left: 4px solid {theme['heading']}; padding-left: 8px")
    for quote in soup.find_all("blockquote"):
        quote.name = "aside"
        set_style(quote, f"background-color: {theme['surface']}; border-left: 4px solid {theme['heading']}; padding: 12px")
    for table in soup.find_all("table"):
        set_style(table, "width: 100%; border-collapse: collapse")
        for header in table.find_all("th"):
            set_style(header, f"background-color: {theme['title']}; color: #FFFFFF; border: 1px solid {theme['border']}; padding: 8px")
        for row_index, row in enumerate(table.find_all("tr")):
            for cell in row.find_all("td"):
                background = f"background-color: {theme['surface_alt']}; " if row_index % 2 == 0 else ""
                set_style(cell, f"{background}border: 1px solid {theme['border']}; padding: 8px")
    for pre in soup.find_all("pre"):
        set_style(pre, f"background-color: {theme['surface_alt']}; border: 1px solid {theme['border']}; padding: 12px; white-space: pre-wrap; overflow-wrap: break-word")
    for code in soup.find_all("code"):
        if code.parent and code.parent.name != "pre":
            set_style(code, f"background-color: {theme['surface_alt']}; border: 1px solid {theme['border']}; padding: 2px")
    for hr in soup.find_all("hr"):
        set_style(hr, f"border-top: 1px solid {theme['border']}")
    first_paragraph = soup.find("p")
    if first_paragraph and not first_paragraph.find_parent(["blockquote", "aside", "table", "details"]):
        set_style(first_paragraph, f"color: {theme['muted']}; font-size: 18px; line-height: 1.8")


def compose(
    input_path: Path,
    title: str,
    output_dir: Path,
    *,
    input_type: str = "auto",
    mode: str = "polish",
    theme_name: str = "emerald",
    image_map_path: Path | None = None,
    navigation: bool = True,
) -> dict[str, Any]:
    if mode not in {"preserve", "polish", "develop"}:
        raise RuntimeError(f"invalid editing mode: {mode}")
    themes = load_themes()
    if theme_name not in themes:
        raise RuntimeError(f"unknown theme: {theme_name}")
    source = input_path.read_text(encoding="utf-8")
    resolved_type = detect_type(input_path, input_type)
    if resolved_type == "html":
        soup = BeautifulSoup(source, "html.parser")
        editable_source = source
    else:
        editable_source = text_to_markdown(source) if resolved_type == "text" else source
        soup = markdown_to_soup(editable_source)
    normalize_headings(soup, title)
    image_map: dict[str, str] = {}
    if image_map_path:
        image_map = json.loads(image_map_path.read_text(encoding="utf-8"))
    images = replace_images(soup, image_map) if soup.find("img") else []
    sections = add_navigation(soup, themes[theme_name]) if navigation else []
    apply_styles(soup, themes[theme_name])
    html = str(soup).strip() + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    source_name = "source.html" if resolved_type == "html" else "post.md"
    write_text(output_dir / source_name, editable_source)
    write_text(output_dir / "post.html", html)
    spec = {
        "schema_version": 1,
        "title": title,
        "source": {"path": input_path.name, "type": resolved_type, "sha256": sha256_text(source)},
        "editing": {"mode": mode},
        "theme": {"name": theme_name},
        "structure": {"navigation": navigation, "body_heading_start": 2, "sections": sections},
        "assets": {"image_map": image_map_path.name if image_map_path else None, "images": images},
        "output": {"html": "post.html", "sha256": sha256_text(html)},
    }
    write_json(output_dir / "post-spec.json", spec)
    return spec
