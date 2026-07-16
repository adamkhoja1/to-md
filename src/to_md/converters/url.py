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


def extract_title(html: str | bytes, url: str) -> str:
    """Extract title from HTML or fall back to URL.

    Accepts raw bytes so trafilatura can detect the page's encoding itself
    (see ``convert``); a pre-decoded ``str`` also works.
    """
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


def dedup_image_tails(markdown: str) -> str:
    """Drop text that trafilatura 2.1.0 duplicates after image embeds.

    For text that follows an inline image within one block (``<p><img/>text</p>``,
    held as the image's lxml ``.tail``), trafilatura 2.1.0's markdown serializer
    emits the tail twice: its graphic branch appends a whitespace-stripped copy to
    the ``![]()`` embed line, then the generic end-of-element tail handler emits
    the same tail again in the paragraph flow. The embed-line copy is a bare
    fragment (inline formatting lost, may stop mid-sentence); the paragraph copy
    is the faithful one — so the fragment is what gets dropped here. Under the
    previously pinned 2.0.0 the same text was silently *lost* instead, which is
    why the pin moved to >=2.1.0 and this guard exists rather than an HTML-level
    workaround.

    DELETE THIS GUARD once the pinned trafilatura release includes upstream
    commit 18a7b42 (already on master: the generic tail handler skips graphic
    tails, ending the double emission — first release after 2.1.0 should have
    it). On fixed versions the guard is already a no-op: the trailing text then
    appears only on the embed line, the following paragraph doesn't repeat it,
    and the startswith check below never fires — so removal is cleanup, not
    urgent.
    """
    lines = markdown.split("\n")
    result = []
    for i, line in enumerate(lines):
        match = re.match(r"(!\[[^\]]*\]\([^)]+\))\s+(\S.*)$", line)
        if match:
            embed, trailing = match.groups()
            following = next((ln for ln in lines[i + 1 :] if ln.strip()), "")
            # Both copies come from the same tail string, so the duplicated
            # paragraph always starts with the embed-line fragment.
            if " ".join(following.split()).startswith(" ".join(trailing.split())):
                result.append(embed)
                continue
        result.append(line)
    return "\n".join(result)


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
        # Pass raw bytes, not response.text: requests defaults undeclared
        # text/html to ISO-8859-1, mojibaking UTF-8 pages. trafilatura detects
        # the real encoding (meta charset + statistics) from the bytes.
        html = response.content
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

    # Workaround for trafilatura 2.1.0 double-emitting image-adjacent text;
    # see dedup_image_tails' docstring for when this can be deleted.
    markdown = dedup_image_tails(markdown)

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
