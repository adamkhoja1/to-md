"""PDF to Markdown converter with multiple backends, image extraction, and chapter splitting."""

import re
from abc import ABC, abstractmethod
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from pydantic import BaseModel

from to_md.core import clean_pdf_text, slugify


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConversionConfig(BaseModel):
    """Configuration for PDF to Markdown conversion."""

    extract_images: bool = True
    split_chapters: bool = False
    image_dir: str = "figures"
    backend: str = "pymupdf"
    use_llm: bool = False
    page_range: tuple[int, int] | None = None


class FontStats(BaseModel):
    """Font size statistics for heading detection."""

    avg_size: float = 12.0
    max_size: float = 12.0


class ConversionResult(BaseModel):
    """Result from a backend conversion."""

    markdown: str
    image_count: int = 0
    files_created: list[str] = []


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def compute_font_stats(doc: fitz.Document) -> FontStats:
    """Compute font size statistics for heading detection."""
    all_sizes: list[float] = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 12)
                        if size > 0:
                            all_sizes.append(size)

    if not all_sizes:
        return FontStats()

    return FontStats(
        avg_size=sum(all_sizes) / len(all_sizes),
        max_size=max(all_sizes),
    )


def detect_heading(span: dict, stats: FontStats) -> tuple[int | None, str]:
    """Detect if a span is a heading. Returns (level, text) or (None, text)."""
    text = span.get("text", "").strip()
    size = span.get("size", 12)
    font = span.get("font", "").lower()

    is_large = size > stats.avg_size * 1.3
    is_bold_large = size > stats.avg_size * 1.1 and "bold" in font

    if is_large or is_bold_large:
        if size > stats.max_size * 0.85:
            return 1, text
        elif size > stats.max_size * 0.7:
            return 2, text
        else:
            return 3, text

    return None, text


MATH_FONT_PREFIXES = (
    "cmmi",
    "cmsy",
    "cmex",
    "lm",
    "stix",
    "math",
    "msam",
    "msbm",
)


def is_math_font(font_name: str) -> bool:
    """Check if a font name indicates a math font (CM, LM, STIX, etc.)."""
    lower = font_name.lower()
    return any(lower.startswith(p) or f"+{p}" in lower for p in MATH_FONT_PREFIXES)


def detect_math_regions(page: fitz.Page) -> list[fitz.Rect]:
    """Detect regions on a page that contain math fonts."""
    math_rects: list[fitz.Rect] = []
    blocks = page.get_text("dict")["blocks"]

    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font = span.get("font", "")
                if is_math_font(font):
                    bbox = span.get("bbox")
                    if bbox:
                        math_rects.append(fitz.Rect(bbox))

    if not math_rects:
        return []

    merged: list[fitz.Rect] = [math_rects[0]]
    for rect in math_rects[1:]:
        expanded = fitz.Rect(merged[-1])
        expanded.y0 -= 2
        expanded.y1 += 2
        expanded.x0 -= 5
        expanded.x1 += 5
        if expanded.intersects(rect):
            merged[-1] = merged[-1] | rect
        else:
            merged.append(rect)

    return merged


# ---------------------------------------------------------------------------
# Backend ABC
# ---------------------------------------------------------------------------


class Backend(ABC):
    """Abstract base class for PDF conversion backends."""

    @abstractmethod
    def convert_page(
        self,
        page: fitz.Page,
        page_num: int,
        stats: FontStats,
        config: ConversionConfig,
    ) -> str:
        """Convert a single page to markdown."""
        ...

    def convert_document(
        self,
        doc: fitz.Document,
        config: ConversionConfig,
        output_dir: Path,
    ) -> ConversionResult:
        """Convert full document. Default implementation iterates pages."""
        stats = compute_font_stats(doc)
        figures_dir = output_dir / config.image_dir

        all_content: list[str] = []
        image_counter = 0
        chapters: list[tuple[str, list[str]]] = []
        current_chapter: tuple[str, list[str]] = ("frontmatter", [])

        start = config.page_range[0] if config.page_range else 0
        end = config.page_range[1] if config.page_range else len(doc)

        for page_num in range(start, min(end, len(doc))):
            page = doc[page_num]
            content = self.convert_page(page, page_num + 1, stats, config)

            image_refs: list[str] = []
            if config.extract_images:
                image_refs, image_counter = extract_images_from_page(
                    page,
                    page_num + 1,
                    len(chapters) + 1 if config.split_chapters else 0,
                    figures_dir,
                    config.image_dir,
                    config.split_chapters,
                    image_counter,
                )

            if image_refs:
                content += "\n" + "\n".join(image_refs)

            if config.split_chapters:
                h1_positions = _find_h1_positions(content)
                if h1_positions:
                    for title in h1_positions:
                        if current_chapter[1]:
                            chapters.append(current_chapter)
                        current_chapter = (title, [])
                    current_chapter[1].append(content)
                else:
                    current_chapter[1].append(content)
            else:
                if content:
                    all_content.append(content)

        files_created: list[str] = []

        if config.split_chapters:
            if current_chapter[1]:
                chapters.append(current_chapter)
            for idx, (title, parts) in enumerate(chapters):
                slug = (
                    slugify(title) if title != "frontmatter" else "00-frontmatter"
                )
                if title != "frontmatter":
                    filename = f"{idx:02d}-{slug}.md"
                else:
                    filename = f"{slug}.md"
                filepath = output_dir / filename
                filepath.write_text("\n\n".join(parts), encoding="utf-8")
                files_created.append(str(filepath))
                print(f"Created: {filepath}")

            return ConversionResult(
                markdown="",
                image_count=image_counter,
                files_created=files_created,
            )
        else:
            markdown = "\n\n".join(all_content)
            return ConversionResult(
                markdown=markdown,
                image_count=image_counter,
            )


def _find_h1_positions(content: str) -> list[str]:
    """Find H1 heading titles in markdown content."""
    titles = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            titles.append(stripped[2:].strip())
    return titles


# ---------------------------------------------------------------------------
# PyMuPDF Backend (default)
# ---------------------------------------------------------------------------


class PyMuPDFBackend(Backend):
    """Default backend using PyMuPDF for text extraction."""

    def convert_page(
        self,
        page: fitz.Page,
        page_num: int,
        stats: FontStats,
        config: ConversionConfig,
    ) -> str:
        blocks = page.get_text("dict")["blocks"]
        parts: list[str] = []

        for block in blocks:
            if block.get("type") != 0:
                continue

            block_parts: list[str] = []
            for line in block.get("lines", []):
                line_parts: list[str] = []
                for span in line.get("spans", []):
                    level, text = detect_heading(span, stats)
                    font = span.get("font", "").lower()

                    if not text:
                        continue

                    if level:
                        formatted = f"\n{'#' * level} {text}\n"
                    elif "bold" in font:
                        formatted = f"**{text}**"
                    elif "italic" in font:
                        formatted = f"*{text}*"
                    else:
                        formatted = text

                    line_parts.append(formatted)

                if line_parts:
                    block_parts.append(" ".join(line_parts))

            if block_parts:
                parts.append(clean_pdf_text("\n".join(block_parts)))

        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Marker Backend
# ---------------------------------------------------------------------------


class MarkerBackend(Backend):
    """Backend using the Marker library for better math extraction."""

    def __init__(self) -> None:
        try:
            from marker.models import create_model_dict  # type: ignore[import-untyped]

            self.artifact_dict = create_model_dict()
        except ImportError:
            raise ImportError(
                "marker-pdf is required for the marker backend. "
                "Install with: pip install marker-pdf"
            )

    def convert_page(
        self,
        page: fitz.Page,
        page_num: int,
        stats: FontStats,
        config: ConversionConfig,
    ) -> str:
        return ""

    def convert_document(
        self,
        doc: fitz.Document,
        config: ConversionConfig,
        output_dir: Path,
    ) -> ConversionResult:
        """Use Marker to convert the entire document at once."""
        from marker.converters.pdf import PdfConverter  # type: ignore[import-untyped]
        from marker.config.parser import ConfigParser  # type: ignore[import-untyped]

        config_dict: dict = {"output_format": "markdown"}
        if config.use_llm:
            config_dict["use_llm"] = True
        if config.page_range:
            pages = ",".join(
                str(p) for p in range(config.page_range[0], config.page_range[1])
            )
            config_dict["page_range"] = pages

        config_parser = ConfigParser(config_dict)
        converter = PdfConverter(
            artifact_dict=self.artifact_dict,
            config=config_parser.generate_config_dict(),
        )

        pdf_path = doc.name
        rendered = converter(pdf_path)
        markdown = rendered.markdown

        image_count = 0
        if config.extract_images and rendered.images:
            figures_dir = output_dir / config.image_dir
            figures_dir.mkdir(parents=True, exist_ok=True)
            for img_name, img in rendered.images.items():
                img_path = figures_dir / img_name
                img.save(str(img_path))
                image_count += 1

        files_created: list[str] = []
        if config.split_chapters:
            chapters = _split_markdown_by_h1(markdown)
            for idx, (title, content) in enumerate(chapters):
                slug = (
                    slugify(title) if title != "frontmatter" else "00-frontmatter"
                )
                if title != "frontmatter":
                    filename = f"{idx:02d}-{slug}.md"
                else:
                    filename = f"{slug}.md"
                filepath = output_dir / filename
                filepath.write_text(content, encoding="utf-8")
                files_created.append(str(filepath))

            return ConversionResult(
                markdown="",
                image_count=image_count,
                files_created=files_created,
            )

        return ConversionResult(markdown=markdown, image_count=image_count)


def _split_markdown_by_h1(markdown: str) -> list[tuple[str, str]]:
    """Split markdown text into chapters at H1 headings."""
    lines = markdown.split("\n")
    chapters: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] = ("frontmatter", [])

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if current[1]:
                chapters.append(current)
            title = stripped[2:].strip()
            current = (title, [line])
        else:
            current[1].append(line)

    if current[1]:
        chapters.append(current)

    return [(title, "\n".join(content)) for title, content in chapters]


# ---------------------------------------------------------------------------
# Surya Hybrid Backend
# ---------------------------------------------------------------------------


class SuryaHybridBackend(Backend):
    """Hybrid backend: PyMuPDF for prose, Surya OCR for math regions."""

    def __init__(self) -> None:
        try:
            from marker.models import create_model_dict  # type: ignore[import-untyped]

            models = create_model_dict()
            self.predictor = models["recognition_model"]
        except ImportError:
            raise ImportError(
                "marker-pdf (or surya-ocr) is required for the surya backend. "
                "Install with: pip install marker-pdf"
            )

    def convert_page(
        self,
        page: fitz.Page,
        page_num: int,
        stats: FontStats,
        config: ConversionConfig,
    ) -> str:
        """Extract prose with PyMuPDF, OCR math regions with Surya."""
        from PIL import Image
        import io

        blocks = page.get_text("dict")["blocks"]
        math_regions = detect_math_regions(page)

        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        page_image = Image.open(io.BytesIO(img_bytes))

        parts: list[str] = []
        pymupdf_backend = PyMuPDFBackend()

        if not math_regions:
            return pymupdf_backend.convert_page(page, page_num, stats, config)

        for block in blocks:
            if block.get("type") != 0:
                continue

            block_rect = fitz.Rect(block["bbox"])
            is_math_block = any(r.intersects(block_rect) for r in math_regions)

            if is_math_block:
                latex = self._ocr_region(page_image, block_rect, page.rect)
                if latex:
                    parts.append(f"$${latex}$$")
                    continue

            block_parts: list[str] = []
            for line in block.get("lines", []):
                line_parts: list[str] = []
                for span in line.get("spans", []):
                    level, text = detect_heading(span, stats)
                    font = span.get("font", "").lower()

                    if not text:
                        continue

                    if level:
                        formatted = f"\n{'#' * level} {text}\n"
                    elif "bold" in font:
                        formatted = f"**{text}**"
                    elif "italic" in font:
                        formatted = f"*{text}*"
                    else:
                        formatted = text

                    line_parts.append(formatted)

                if line_parts:
                    block_parts.append(" ".join(line_parts))

            if block_parts:
                parts.append(clean_pdf_text("\n".join(block_parts)))

        return "\n\n".join(parts)

    def _ocr_region(
        self,
        page_image: "Image.Image",  # type: ignore[name-defined]
        block_rect: fitz.Rect,
        page_rect: fitz.Rect,
    ) -> str:
        """OCR a specific region of the page image using Surya."""
        scale_x = page_image.width / page_rect.width
        scale_y = page_image.height / page_rect.height

        left = int(block_rect.x0 * scale_x)
        top = int(block_rect.y0 * scale_y)
        right = int(block_rect.x1 * scale_x)
        bottom = int(block_rect.y1 * scale_y)

        cropped = page_image.crop((left, top, right, bottom))

        try:
            results = self.predictor([cropped], math_mode=True)
            if results and results[0].text_lines:
                return " ".join(line.text for line in results[0].text_lines)
        except Exception:
            pass

        return ""


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

BACKENDS: dict[str, type[Backend]] = {
    "pymupdf": PyMuPDFBackend,
    "marker": MarkerBackend,
    "surya": SuryaHybridBackend,
}


def get_backend(name: str) -> Backend:
    """Get a backend instance by name."""
    cls = BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"Unknown backend: {name!r}. Available: {list(BACKENDS)}")
    return cls()


# ---------------------------------------------------------------------------
# Image extraction (shared across backends)
# ---------------------------------------------------------------------------


def extract_images_from_page(
    page: fitz.Page,
    page_num: int,
    chapter_num: int,
    figures_dir: Path,
    image_dir_name: str,
    split_chapters: bool,
    image_counter: int,
) -> tuple[list[str], int]:
    """Extract images from a page. Returns (markdown_refs, updated_counter)."""
    images: list[str] = []
    image_list = page.get_images()

    for img_idx, img in enumerate(image_list):
        xref = img[0]
        base_image = page.parent.extract_image(xref)
        if not base_image:
            continue

        image_bytes = base_image["image"]
        image_ext = base_image.get("ext", "png")

        image_counter += 1
        if split_chapters:
            img_name = f"fig_{chapter_num:02d}_{image_counter:03d}.{image_ext}"
        else:
            img_name = f"fig_{page_num:03d}_{img_idx:02d}.{image_ext}"

        figures_dir.mkdir(parents=True, exist_ok=True)
        img_path = figures_dir / img_name
        img_path.write_bytes(image_bytes)

        rel_path = f"{image_dir_name}/{img_name}"
        images.append(f"\n![Figure {image_counter}]({rel_path})\n")

    return images, image_counter


# ---------------------------------------------------------------------------
# Main conversion entry point
# ---------------------------------------------------------------------------


def convert(
    input_pdf: str,
    output: str,
    split_chapters: bool = False,
    no_images: bool = False,
    image_dir: str = "figures",
    backend: str = "pymupdf",
    use_llm: bool = False,
    page_range: str = "",
) -> None:
    """Convert PDF to Markdown with image extraction and chapter splitting.

    Args:
        input_pdf: Path to input PDF file.
        output: Output file (.md) or directory.
        split_chapters: Split into separate files at H1 headings.
        no_images: Skip image extraction.
        image_dir: Name of figures directory.
        backend: Conversion backend (pymupdf, marker, surya).
        use_llm: Enable LLM-assisted conversion (marker backend).
        page_range: Page range as "start-end" (0-indexed, inclusive).
    """
    pdf_path = Path(input_pdf).resolve()
    output_path = Path(output)

    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    parsed_range = None
    if page_range:
        parts = page_range.split("-")
        parsed_range = (int(parts[0]), int(parts[1]) + 1)

    config = ConversionConfig(
        extract_images=not no_images,
        split_chapters=split_chapters,
        image_dir=image_dir,
        backend=backend,
        use_llm=use_llm,
        page_range=parsed_range,
    )

    if output_path.suffix == ".md":
        output_dir = output_path.parent
        single_file = output_path
    else:
        output_dir = output_path
        single_file = None

    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    backend_instance = get_backend(config.backend)
    result = backend_instance.convert_document(doc, config, output_dir)
    doc.close()

    if not config.split_chapters and result.markdown:
        output_file = single_file or (output_dir / "output.md")
        output_file.write_text(result.markdown, encoding="utf-8")
        print(f"Created: {output_file}")

    if config.extract_images and result.image_count > 0:
        figures_dir = output_dir / config.image_dir
        print(f"Extracted {result.image_count} images to: {figures_dir}/")
