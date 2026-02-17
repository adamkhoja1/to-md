"""Convert .docx files to clean markdown.

Uses pandoc if available, falls back to mammoth + markdownify.
"""

import re
import shutil
import subprocess
from glob import glob
from pathlib import Path

from to_md.core import has_pandoc


def _strip_images(text: str) -> str:
    """Remove markdown image references and collapse leftover blank lines."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)\s*\n?", "", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _convert_with_pandoc(src: Path, dst: Path) -> None:
    result = subprocess.run(
        ["pandoc", str(src), "-f", "docx", "-t", "gfm", "--wrap=none"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or f"pandoc exited with code {result.returncode}"
        )
    markdown = _strip_images(result.stdout)
    dst.write_text(markdown, encoding="utf-8")


def _convert_with_mammoth(src: Path, dst: Path) -> None:
    import mammoth  # type: ignore[import-untyped]
    from markdownify import markdownify as md  # type: ignore[import-untyped]

    with open(src, "rb") as f:
        result = mammoth.convert_to_html(f)

    for msg in result.messages:
        print(f"    warning: {msg}")

    markdown = md(result.value, heading_style="atx", strip=["img"])
    dst.write_text(markdown, encoding="utf-8")


def convert(source: str, output_dir: str | None = None) -> None:
    """Convert .docx file(s) to markdown.

    Args:
        source: Path to a .docx file or glob pattern (e.g. "docs/*.docx").
        output_dir: Optional output directory. Defaults to same directory as source.
    """
    files = sorted(Path(p) for p in glob(source, recursive=True))
    if not files:
        p = Path(source)
        if p.exists():
            files = [p]
        else:
            raise FileNotFoundError(f"No files matched: {source}")

    files = [f for f in files if f.suffix.lower() == ".docx"]
    if not files:
        raise FileNotFoundError(f"No .docx files found in: {source}")

    use_pandoc = has_pandoc()
    engine = "pandoc" if use_pandoc else "mammoth"
    print(f"Using {engine} for conversion ({len(files)} file(s))")

    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    failed = 0
    seen_names: dict[str, Path] = {}

    for src in files:
        if out_dir:
            name = src.with_suffix(".md").name
            if name in seen_names:
                stem = src.with_suffix("").name
                parent_slug = src.parent.name or "root"
                name = f"{parent_slug}_{stem}.md"
            seen_names[name] = src
            dst = out_dir / name
        else:
            dst = src.with_suffix(".md")

        try:
            if use_pandoc:
                _convert_with_pandoc(src, dst)
            else:
                _convert_with_mammoth(src, dst)
            print(f"  {src} -> {dst}")
            converted += 1
        except Exception as e:
            print(f"  FAILED {src}: {e}")
            failed += 1

    print(f"\nDone: {converted} converted, {failed} failed")
