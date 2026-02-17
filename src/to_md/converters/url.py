"""URL to Markdown converter with image extraction and section splitting."""

import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests  # type: ignore[import-untyped]
from pydantic import BaseModel

from to_md.core import slugify


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConversionConfig(BaseModel):
    """Configuration for URL to Markdown conversion."""

    extract_images: bool = False
    split_sections: bool = False
    image_dir: str = "figures"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def extract_title(html: str, url: str) -> str:
    """Extract title from HTML or fall back to URL."""
    import trafilatura  # type: ignore[import-untyped]

    metadata = trafilatura.extract_metadata(html)
    if metadata and metadata.title:
        return metadata.title

    path = urlparse(url).path.strip("/")
    if path:
        return path.split("/")[-1].replace("-", " ").replace("_", " ").title()

    return "Untitled"


def download_image(img_url: str, figures_dir: Path, index: int) -> str | None:
    """Download an image and return the local filename."""
    try:
        response = requests.get(
            img_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; to-md/1.0)"},
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "png" in content_type:
            ext = "png"
        elif "gif" in content_type:
            ext = "gif"
        elif "webp" in content_type:
            ext = "webp"
        elif "svg" in content_type:
            ext = "svg"
        else:
            ext = "jpg"

        url_hash = hashlib.md5(img_url.encode()).hexdigest()[:8]
        filename = f"fig_{index:03d}_{url_hash}.{ext}"

        figures_dir.mkdir(parents=True, exist_ok=True)
        (figures_dir / filename).write_bytes(response.content)

        return filename
    except Exception:
        return None


def extract_images_from_markdown(
    markdown: str, base_url: str, figures_dir: Path, image_dir_name: str
) -> str:
    """Find images in markdown, download them, and rewrite paths."""
    img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    downloaded = 0

    def replace_image(match: re.Match) -> str:
        nonlocal downloaded
        alt_text = match.group(1)
        img_url = match.group(2)

        if img_url.startswith("data:"):
            return ""

        if not img_url.startswith(("http://", "https://")):
            img_url = urljoin(base_url, img_url)

        downloaded += 1
        filename = download_image(img_url, figures_dir, downloaded)

        if filename:
            return f"![{alt_text}]({image_dir_name}/{filename})"
        return ""

    return img_pattern.sub(replace_image, markdown)


def split_by_headings(markdown: str, title: str) -> list[tuple[str, str]]:
    """Split markdown into sections by H1/H2 headings."""
    sections: list[tuple[str, str]] = []

    pattern = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)
    parts = pattern.split(markdown)

    if parts[0].strip():
        sections.append((title, parts[0].strip()))

    i = 1
    while i < len(parts) - 2:
        heading_text = parts[i + 1].strip()
        content = parts[i + 2].strip() if i + 2 < len(parts) else ""
        if heading_text and content:
            sections.append((heading_text, f"# {heading_text}\n\n{content}"))
        i += 3

    return sections if sections else [(title, markdown)]


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def convert(
    url: str,
    output: str | None = None,
    images: bool = False,
    split: bool = False,
    image_dir: str = "figures",
) -> None:
    """Convert a URL to clean Markdown.

    Args:
        url: The URL to fetch and convert.
        output: Output file (.md) or directory. Auto-generated if omitted.
        images: Download images to figures/ directory.
        split: Split into separate files at H1/H2 headings.
        image_dir: Name of figures directory.
    """
    import trafilatura  # type: ignore[import-untyped]

    config = ConversionConfig(
        extract_images=images,
        split_sections=split,
        image_dir=image_dir,
    )

    print(f"Fetching: {url}")
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; to-md/1.0)"},
        )
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        raise SystemExit(f"Failed to fetch URL: {e}")

    title = extract_title(html, url)
    slug = slugify(title, max_len=60)

    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=False,
        include_images=config.extract_images,
        include_tables=True,
        include_comments=False,
        favor_recall=True,
    )

    if not markdown:
        raise SystemExit("Failed to extract content from URL")

    if not markdown.startswith("#"):
        markdown = f"# {title}\n\n{markdown}"

    if output:
        output_path = Path(output)
        if output_path.suffix == ".md":
            output_dir = output_path.parent
            single_file = output_path
        else:
            output_dir = output_path
            single_file = None
    else:
        if config.extract_images or config.split_sections:
            output_dir = Path(slug)
            single_file = None
        else:
            output_dir = Path(".")
            single_file = Path(f"{slug}.md")

    figures_dir = output_dir / config.image_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if config.extract_images:
        markdown = extract_images_from_markdown(
            markdown, url, figures_dir, config.image_dir
        )
        if figures_dir.exists() and any(figures_dir.iterdir()):
            print(f"Downloaded images to: {figures_dir}/")

    if config.split_sections:
        sections = split_by_headings(markdown, title)
        for idx, (section_title, content) in enumerate(sections):
            section_slug = slugify(section_title)
            filename = f"{idx:02d}-{section_slug}.md"
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            print(f"Created: {filepath}")
    else:
        output_file = single_file or (output_dir / f"{slug}.md")
        output_file.write_text(markdown, encoding="utf-8")
        print(f"Created: {output_file}")
