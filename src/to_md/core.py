"""Shared models and utilities for all converters."""

import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConversionResult(BaseModel):
    """Result from any conversion."""

    files_created: list[str] = []
    figure_count: int = 0
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len].strip("-") or "untitled"


def clean_text(text: str) -> str:
    """Clean up common conversion artifacts (collapse whitespace, limit blank lines)."""
    if not text:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_pdf_text(text: str) -> str:
    """Clean up PDF-specific extraction artifacts (dehyphenation, ligatures)."""
    if not text:
        return ""
    # Dehyphenate line-broken words
    text = re.sub(r"(?<=[a-z])-\s*\n\s*(?=[a-z])", "", text)
    # Fix common ligature encoding issues
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff")
    text = clean_text(text)
    return text


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------


def split_by_sections(
    md: str, heading_level: int = 1, default_title: str = "abstract"
) -> list[tuple[str, str]]:
    """Split markdown at headings into (title, content) pairs.

    Args:
        md: Markdown text.
        heading_level: Heading level to split on (1 = H1, 2 = H1/H2).
        default_title: Title for content before the first heading.
    """
    lines = md.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] = (default_title, [])

    prefix = "#" * heading_level + " "
    next_prefix = "#" * (heading_level + 1) + " "

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) and not stripped.startswith(next_prefix):
            if current[1] or sections:
                sections.append(current)
            title = stripped[len(prefix) :].strip()
            current = (title, [line])
        else:
            current[1].append(line)

    if current[1]:
        sections.append(current)

    if not sections:
        return [("output", md)]

    return [(title, "\n".join(content)) for title, content in sections]


# ---------------------------------------------------------------------------
# Image path fixing
# ---------------------------------------------------------------------------


def fix_image_paths(md: str, path_map: dict[str, str]) -> str:
    """Rewrite image paths in markdown using a mapping dict.

    Tries exact match, then basename, then stem.
    """

    def replace_image(match: re.Match) -> str:
        alt = match.group(1)
        old_path = match.group(2)
        new_path = path_map.get(old_path)
        if not new_path:
            new_path = path_map.get(Path(old_path).name)
        if not new_path:
            new_path = path_map.get(Path(old_path).stem)
        if new_path:
            return f"![{alt}]({new_path})"
        return match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_image, md)


# ---------------------------------------------------------------------------
# Table conversion
# ---------------------------------------------------------------------------


def table_to_markdown(table: list[list[str | None]]) -> str:
    """Convert a table (list of rows) to markdown format."""
    if not table or not table[0]:
        return ""

    def clean_cell(cell: str | None) -> str:
        if cell is None:
            return ""
        return str(cell).replace("\n", " ").replace("|", "\\|").strip()

    header_cells = [clean_cell(cell) for cell in table[0]]
    header = "| " + " | ".join(header_cells) + " |"
    separator = "| " + " | ".join("---" for _ in header_cells) + " |"

    rows = []
    for row in table[1:]:
        cells = [clean_cell(cell) for cell in row]
        while len(cells) < len(header_cells):
            cells.append("")
        rows.append("| " + " | ".join(cells[: len(header_cells)]) + " |")

    return "\n".join([header, separator] + rows)


# ---------------------------------------------------------------------------
# Pandoc wrapper
# ---------------------------------------------------------------------------


def has_pandoc() -> bool:
    """Check if pandoc is available on PATH."""
    return shutil.which("pandoc") is not None


def run_pandoc(
    input_path: str | Path,
    from_fmt: str,
    to_fmt: str = "gfm",
    extra_args: list[str] | None = None,
    timeout: int = 120,
    cwd: str | Path | None = None,
) -> str:
    """Run pandoc and return output as string.

    Returns markdown string or raises RuntimeError on failure.
    """
    if not has_pandoc():
        raise RuntimeError(
            "pandoc is required but not found. Install from https://pandoc.org/"
        )

    cmd = [
        "pandoc",
        str(input_path),
        "-f",
        from_fmt,
        "-t",
        to_fmt,
        "--wrap=none",
    ]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Pandoc timed out after {timeout}s")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if result.stdout:
            print(f"Pandoc warnings: {stderr}")
            return result.stdout
        raise RuntimeError(
            f"Pandoc failed (exit {result.returncode}): {stderr or '(no error output)'}"
        )
    return result.stdout
