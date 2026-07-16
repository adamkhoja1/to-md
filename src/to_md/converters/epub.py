"""EPUB to Markdown converter with image extraction and chapter splitting."""

import re
from pathlib import Path

import ebooklib  # type: ignore[import-untyped]
from bs4 import BeautifulSoup, Tag  # type: ignore[import-untyped]
from ebooklib import epub  # type: ignore[import-untyped]
from pydantic import BaseModel

from to_md.core import slugify


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EpubConfig(BaseModel):
    """Configuration for EPUB conversion."""

    image_dir: str = "figures"
    extract_images: bool = True


# ---------------------------------------------------------------------------
# HTML to Markdown conversion
# ---------------------------------------------------------------------------


def html_to_md(html: str) -> str:
    """Convert HTML content to markdown."""
    soup = BeautifulSoup(html, "html.parser")
    return _convert_element(soup)


def _convert_element(element: Tag | str) -> str:
    """Recursively convert an HTML element to markdown."""
    if isinstance(element, str):
        return element

    if not isinstance(element, Tag):
        return str(element)

    tag = element.name

    if tag is None:
        return element.get_text()

    if tag in ("script", "style"):
        return ""

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = element.get_text().strip()
        return f"\n{'#' * level} {text}\n\n"

    if tag == "p":
        children = "".join(_convert_element(c) for c in element.children)
        return f"\n{children.strip()}\n\n"

    if tag in ("b", "strong"):
        text = element.get_text().strip()
        return f"**{text}**" if text else ""

    if tag in ("i", "em"):
        text = element.get_text().strip()
        return f"*{text}*" if text else ""

    if tag == "a":
        text = element.get_text().strip()
        href = element.get("href", "")
        return f"[{text}]({href})" if text else ""

    if tag == "img":
        src = element.get("src", "")
        alt = element.get("alt", "")
        return f"![{alt}]({src})"

    if tag == "ul":
        items = []
        for li in element.find_all("li", recursive=False):
            text = _convert_element(li).strip()
            items.append(f"- {text}")
        return "\n" + "\n".join(items) + "\n\n"

    if tag == "ol":
        items = []
        for i, li in enumerate(element.find_all("li", recursive=False), 1):
            text = _convert_element(li).strip()
            items.append(f"{i}. {text}")
        return "\n" + "\n".join(items) + "\n\n"

    if tag == "table":
        return _table_to_md(element)

    if tag == "blockquote":
        text = "".join(_convert_element(c) for c in element.children).strip()
        lines = text.split("\n")
        return "\n" + "\n".join(f"> {line}" for line in lines) + "\n\n"

    if tag == "pre":
        code = element.get_text()
        return f"\n```\n{code}\n```\n\n"

    if tag == "code":
        return f"`{element.get_text()}`"

    if tag == "br":
        return "\n"

    if tag == "hr":
        return "\n---\n\n"

    if tag == "sup":
        text = element.get_text().strip()
        return f"[^{text}]"

    return "".join(_convert_element(c) for c in element.children)


def _table_to_md(table: Tag) -> str:
    """Convert an HTML table to markdown."""
    rows: list[list[str]] = []

    for tr in table.find_all("tr"):
        cells = []
        for td in tr.find_all(["td", "th"]):
            cells.append(td.get_text().strip().replace("|", "\\|"))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    max_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body_rows = ["| " + " | ".join(row) + " |" for row in rows[1:]]

    return "\n" + "\n".join([header, separator] + body_rows) + "\n\n"


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------


def extract_epub_images(
    book: epub.EpubBook, output_dir: Path, image_dir: str
) -> dict[str, str]:
    """Extract images from EPUB. Returns mapping of original path -> new path."""
    figures_dir = output_dir / image_dir
    path_map: dict[str, str] = {}

    for item in book.get_items():
        # ITEM_IMAGE is 1 (a magic 3 here would select ITEM_SCRIPT);
        # covers are typed separately as ITEM_COVER.
        if item.get_type() in (ebooklib.ITEM_IMAGE, ebooklib.ITEM_COVER):
            original_name = Path(item.get_name()).name
            figures_dir.mkdir(parents=True, exist_ok=True)
            img_path = figures_dir / original_name
            img_path.write_bytes(item.get_content())
            path_map[item.get_name()] = f"{image_dir}/{original_name}"

    return path_map


def _fix_image_paths(markdown: str, path_map: dict[str, str]) -> str:
    """Rewrite EPUB-internal image targets to their extracted paths.

    Embed targets are whatever the source ``<img src>`` was — full EPUB-internal
    path or bare basename. Rewrite them in a single pass scoped to image embeds,
    so an already-rewritten path is never re-scanned (cascading ``str.replace``
    doubled the prefix) and prose mentioning a filename is left alone.
    """
    by_name: dict[str, str] = {}
    for original, new_path in path_map.items():
        by_name[original] = new_path
        by_name[Path(original).name] = new_path

    def repl(match: re.Match[str]) -> str:
        alt, target = match.group(1), match.group(2).strip()
        hit = by_name.get(target) or by_name.get(target.rsplit("/", 1)[-1])
        return f"![{alt}]({hit})" if hit else match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", repl, markdown)


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def convert(
    input_epub: str,
    output: str,
    no_images: bool = False,
    image_dir: str = "figures",
) -> None:
    """Convert EPUB to Markdown files.

    Each EPUB chapter becomes a separate numbered markdown file.

    Args:
        input_epub: Path to input EPUB file.
        output: Output directory.
        no_images: Skip image extraction.
        image_dir: Name of figures directory.
    """
    epub_path = Path(input_epub).resolve()
    output_dir = Path(output).resolve()

    if not epub_path.exists():
        raise FileNotFoundError(f"File not found: {epub_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    config = EpubConfig(image_dir=image_dir, extract_images=not no_images)

    book = epub.read_epub(str(epub_path))

    # Extract images first
    path_map: dict[str, str] = {}
    if config.extract_images:
        path_map = extract_epub_images(book, output_dir, config.image_dir)
        if path_map:
            print(
                f"Extracted {len(path_map)} images to {output_dir / config.image_dir}/"
            )

    # Process chapters
    chapters = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    if not chapters:
        spine_ids = [item_id for item_id, _ in book.spine]
        chapters = [book.get_item_with_id(item_id) for item_id in spine_ids]
        chapters = [c for c in chapters if c is not None]

    file_count = 0
    for idx, chapter in enumerate(chapters):
        content = chapter.get_content().decode("utf-8", errors="replace")
        markdown = html_to_md(content)

        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

        if not markdown or len(markdown) < 10:
            continue

        if path_map:
            markdown = _fix_image_paths(markdown, path_map)

        filename = f"{idx:02d}-chapter.md"

        title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if title_match:
            slug = slugify(title_match.group(1))
            if slug:
                filename = f"{idx:02d}-{slug}.md"

        filepath = output_dir / filename
        filepath.write_text(markdown, encoding="utf-8")
        print(f"Created: {filepath}")
        file_count += 1

    print(f"\nConverted {file_count} chapters.")
