"""Convert .docx files to clean markdown.

Uses pandoc if available, falls back to mammoth + markdownify.

Images are extracted to a ``figures/`` directory by default (matching the other
converters); pass ``no_images=True`` to strip them instead.
"""

import re
import shutil
import subprocess
import tempfile
from glob import glob
from pathlib import Path

from to_md.core import fix_image_paths, has_pandoc


def _strip_images(text: str) -> str:
    """Remove markdown + HTML image references and collapse leftover blank lines."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)\s*\n?", "", text)
    text = re.sub(r"<img\b[^>]*>\s*\n?", "", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _html_img_to_markdown(text: str) -> str:
    """Normalize pandoc's raw ``<img src="..." alt="...">`` tags to markdown images."""

    def repl(match: re.Match) -> str:
        attrs = match.group(1)
        src_m = re.search(r'src="([^"]*)"', attrs)
        alt_m = re.search(r'alt="([^"]*)"', attrs)
        if not src_m:
            return match.group(0)
        alt = alt_m.group(1) if alt_m else ""
        return f"![{alt}]({src_m.group(1)})"

    return re.sub(r"<img\b([^>]*?)/?>", repl, text)


def _extract_pandoc_media(
    markdown: str,
    staging: Path,
    figures_dir: Path,
    image_dir: str,
    name_stem: str,
) -> str:
    """Copy pandoc-extracted media into ``figures_dir`` with clean names.

    Returns the markdown with image links rewritten to ``image_dir/...``. Names are
    prefixed with ``name_stem`` so batch conversions don't collide in a shared dir.
    """
    media_files = sorted(p for p in staging.rglob("*") if p.is_file())
    if not media_files:
        return markdown

    figures_dir.mkdir(parents=True, exist_ok=True)
    path_map: dict[str, str] = {}
    for idx, src in enumerate(media_files, 1):
        ext = src.suffix.lower() or ".png"
        out_name = f"{name_stem}_{idx:02d}{ext}"
        shutil.copy2(src, figures_dir / out_name)
        rel = f"{image_dir}/{out_name}"
        # Pandoc emits links by the extracted file's path; match on name/stem.
        path_map[src.name] = rel
        path_map[src.stem] = rel

    # Pandoc's gfm writer emits images as raw <img> tags; normalize to markdown
    # first, then rewrite the (often absolute, soon-deleted) paths to figures/.
    markdown = _html_img_to_markdown(markdown)
    return fix_image_paths(markdown, path_map)


def _convert_with_pandoc(
    src: Path, dst: Path, extract_images: bool = True, image_dir: str = "figures"
) -> None:
    cmd = ["pandoc", str(src), "-f", "docx", "-t", "gfm", "--wrap=none"]
    staging: Path | None = None
    if extract_images:
        staging = Path(tempfile.mkdtemp(prefix="to_md_docx_"))
        cmd += ["--extract-media", str(staging)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or f"pandoc exited with code {result.returncode}"
            )
        markdown = result.stdout
        if extract_images and staging is not None:
            markdown = _extract_pandoc_media(
                markdown, staging, dst.parent / image_dir, image_dir, dst.stem
            )
            markdown = _collapse_blank_lines(markdown)
        else:
            markdown = _strip_images(markdown)
        dst.write_text(markdown, encoding="utf-8")
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _convert_with_mammoth(
    src: Path, dst: Path, extract_images: bool = True, image_dir: str = "figures"
) -> None:
    import mammoth  # type: ignore[import-untyped]
    from markdownify import markdownify as md  # type: ignore[import-untyped]

    if extract_images:
        figures_dir = dst.parent / image_dir
        counter = {"n": 0}

        @mammoth.images.img_element
        def _store_image(image):  # type: ignore[no-untyped-def]
            counter["n"] += 1
            subtype = (image.content_type or "image/png").split("/")[-1].lower()
            ext = {"jpeg": "jpg"}.get(subtype, subtype)
            out_name = f"{dst.stem}_{counter['n']:02d}.{ext}"
            figures_dir.mkdir(parents=True, exist_ok=True)
            with image.open() as image_bytes:
                (figures_dir / out_name).write_bytes(image_bytes.read())
            return {"src": f"{image_dir}/{out_name}"}

        with open(src, "rb") as f:
            result = mammoth.convert_to_html(f, convert_image=_store_image)
        for msg in result.messages:
            print(f"    warning: {msg}")
        markdown = _collapse_blank_lines(md(result.value, heading_style="atx"))
    else:
        with open(src, "rb") as f:
            result = mammoth.convert_to_html(f)
        for msg in result.messages:
            print(f"    warning: {msg}")
        markdown = md(result.value, heading_style="atx", strip=["img"])

    dst.write_text(markdown, encoding="utf-8")


def convert(
    source: str,
    output_dir: str | None = None,
    no_images: bool = False,
    image_dir: str = "figures",
) -> None:
    """Convert .docx file(s) to markdown.

    Args:
        source: Path to a .docx file or glob pattern (e.g. "docs/*.docx").
        output_dir: Optional output directory. Defaults to same directory as source.
        no_images: Strip images instead of extracting them to image_dir/.
        image_dir: Name of the figures directory for extracted images.
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

    extract_images = not no_images
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
                _convert_with_pandoc(src, dst, extract_images, image_dir)
            else:
                _convert_with_mammoth(src, dst, extract_images, image_dir)
            print(f"  {src} -> {dst}")
            converted += 1
        except Exception as e:
            print(f"  FAILED {src}: {e}")
            failed += 1

    print(f"\nDone: {converted} converted, {failed} failed")
