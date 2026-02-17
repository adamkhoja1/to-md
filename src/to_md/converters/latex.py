"""LaTeX to Markdown converter with arXiv support, citation processing, and figure conversion."""

import io
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from pydantic import BaseModel

from to_md.core import (
    ConversionResult,
    clean_text,
    fix_image_paths,
    slugify,
    split_by_sections,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConversionConfig(BaseModel):
    """Configuration for LaTeX to Markdown conversion."""

    split: bool = True
    figures: bool = True
    image_dir: str = "figures"
    bib: bool = True
    flatten_only: bool = False


class InputContext(BaseModel):
    """Resolved input context with paths to all project files."""

    project_dir: Path
    main_tex: Path
    bib_files: list[Path] = []
    figure_files: list[Path] = []
    is_temp: bool = False

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Stage 1: Resolve input
# ---------------------------------------------------------------------------

ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|e-print)/(\d{4}\.\d{4,5}(?:v\d+)?)"
)
FIGURE_EXTS = {"*.eps", "*.pdf", "*.png", "*.jpg", "*.jpeg", "*.svg"}
FIGURE_DIRS = ["figures", "figs", "images", "img", "fig", "."]


def _detect_arxiv_id(source: str) -> str | None:
    """Extract arXiv ID from a string (ID or URL)."""
    m = ARXIV_ID_RE.match(source.strip())
    if m:
        return m.group(0)
    m = ARXIV_URL_RE.search(source)
    if m:
        return m.group(1)
    return None


def _download_arxiv(arxiv_id: str, tmpdir: Path) -> Path:
    """Download and extract arXiv source."""
    import requests  # type: ignore[import-untyped]

    url = f"https://arxiv.org/e-print/{arxiv_id}"
    print(f"Downloading arXiv source: {url}")
    resp = requests.get(url, timeout=60, headers={"User-Agent": "to-md/1.0"})
    if resp.status_code == 404:
        raise FileNotFoundError(
            f"arXiv source not found for {arxiv_id}. "
            "The source may not be available. Try pdf-to-markdown instead."
        )
    resp.raise_for_status()

    content = resp.content
    extract_dir = tmpdir / "source"
    extract_dir.mkdir()

    # arXiv e-print can be tar.gz, gz (single file), or plain tex
    if content[:2] == b"\x1f\x8b":  # gzip magic
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                tar.extractall(extract_dir, filter="data")
            return extract_dir
        except tarfile.TarError:
            import gzip

            tex_content = gzip.decompress(content)
            tex_file = extract_dir / "main.tex"
            tex_file.write_bytes(tex_content)
            return extract_dir
    else:
        tex_file = extract_dir / "main.tex"
        tex_file.write_bytes(content)
        return extract_dir


def _find_main_tex(project_dir: Path) -> Path:
    """Find the main .tex file in a project directory."""
    tex_files = list(project_dir.rglob("*.tex"))
    if not tex_files:
        raise FileNotFoundError(f"No .tex files found in {project_dir}")

    if len(tex_files) == 1:
        return tex_files[0]

    # Prefer file with \begin{document}
    candidates = []
    for f in tex_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        if r"\begin{document}" in content:
            candidates.append(f)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = [str(c.relative_to(project_dir)) for c in candidates]
        raise ValueError(
            f"Multiple main .tex files found: {names}. "
            "Please specify the main .tex file directly."
        )

    # No \begin{document} found, look for \documentclass
    for f in tex_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        if r"\documentclass" in content:
            return f

    return tex_files[0]


def _discover_figures(project_dir: Path) -> list[Path]:
    """Discover figure files in common locations."""
    figures: list[Path] = []
    for fig_dir_name in FIGURE_DIRS:
        fig_dir = project_dir / fig_dir_name if fig_dir_name != "." else project_dir
        if not fig_dir.is_dir():
            continue
        for ext in FIGURE_EXTS:
            figures.extend(fig_dir.glob(ext))
    return sorted(set(figures))


def resolve_input(source: str) -> InputContext:
    """Resolve input source to an InputContext."""
    arxiv_id = _detect_arxiv_id(source)
    if arxiv_id:
        tmpdir = Path(tempfile.mkdtemp(prefix="latex2md_"))
        project_dir = _download_arxiv(arxiv_id, tmpdir)
        main_tex = _find_main_tex(project_dir)
        bib_files = sorted(project_dir.rglob("*.bib"))
        figure_files = _discover_figures(project_dir)
        return InputContext(
            project_dir=project_dir,
            main_tex=main_tex,
            bib_files=bib_files,
            figure_files=figure_files,
            is_temp=True,
        )

    source_path = Path(source).resolve()

    # ZIP file (Overleaf export)
    if source_path.suffix == ".zip":
        tmpdir = Path(tempfile.mkdtemp(prefix="latex2md_"))
        extract_dir = tmpdir / "source"
        with zipfile.ZipFile(source_path) as zf:
            zf.extractall(extract_dir)
        main_tex = _find_main_tex(extract_dir)
        bib_files = sorted(extract_dir.rglob("*.bib"))
        figure_files = _discover_figures(extract_dir)
        return InputContext(
            project_dir=extract_dir,
            main_tex=main_tex,
            bib_files=bib_files,
            figure_files=figure_files,
            is_temp=True,
        )

    # tar.gz file
    if source_path.name.endswith(".tar.gz") or source_path.suffix == ".tgz":
        tmpdir = Path(tempfile.mkdtemp(prefix="latex2md_"))
        extract_dir = tmpdir / "source"
        extract_dir.mkdir()
        with tarfile.open(source_path) as tar:
            tar.extractall(extract_dir, filter="data")
        main_tex = _find_main_tex(extract_dir)
        bib_files = sorted(extract_dir.rglob("*.bib"))
        figure_files = _discover_figures(extract_dir)
        return InputContext(
            project_dir=extract_dir,
            main_tex=main_tex,
            bib_files=bib_files,
            figure_files=figure_files,
            is_temp=True,
        )

    # Direct .tex file
    if source_path.suffix == ".tex":
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")
        project_dir = source_path.parent
        bib_files = sorted(project_dir.rglob("*.bib"))
        figure_files = _discover_figures(project_dir)
        return InputContext(
            project_dir=project_dir,
            main_tex=source_path,
            bib_files=bib_files,
            figure_files=figure_files,
            is_temp=False,
        )

    raise ValueError(
        f"Unsupported input: {source}. "
        "Expected: arXiv ID, arXiv URL, .tex file, .zip, or .tar.gz"
    )


# ---------------------------------------------------------------------------
# Stage 2: Flatten LaTeX
# ---------------------------------------------------------------------------

INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")


def flatten_latex(
    tex_path: Path, project_dir: Path, _visited: set[Path] | None = None
) -> str:
    """Recursively resolve \\input{} and \\include{} to produce a single flattened .tex."""
    if _visited is None:
        _visited = set()

    resolved = tex_path.resolve()
    if resolved in _visited:
        return f"% WARNING: circular include skipped: {tex_path}\n"
    _visited.add(resolved)

    if not tex_path.exists():
        return f"% WARNING: file not found: {tex_path}\n"

    content = tex_path.read_text(encoding="utf-8", errors="replace")

    def replace_input(match: re.Match) -> str:
        included_name = match.group(1)
        if not included_name.endswith(".tex"):
            included_name += ".tex"
        included_path = project_dir / included_name
        if not included_path.exists():
            included_path = tex_path.parent / included_name
        if not included_path.exists():
            return f"% WARNING: included file not found: {included_name}\n"
        return flatten_latex(included_path, project_dir, _visited)

    return INPUT_RE.sub(replace_input, content)


# ---------------------------------------------------------------------------
# Stage 3: Run pandoc
# ---------------------------------------------------------------------------


def _find_bib_from_tex(content: str, project_dir: Path) -> Path | None:
    """Find .bib file referenced in \\bibliography{} or \\addbibresource{}."""
    patterns = [
        re.compile(r"\\bibliography\{([^}]+)\}"),
        re.compile(r"\\addbibresource\{([^}]+)\}"),
    ]
    for pat in patterns:
        m = pat.search(content)
        if m:
            bib_name = m.group(1).strip()
            if not bib_name.endswith(".bib"):
                bib_name += ".bib"
            bib_path = project_dir / bib_name
            if bib_path.exists():
                return bib_path
    return None


def _run_pandoc_cmd(cmd: list[str], cwd: Path, timeout: int) -> str | None:
    """Run a pandoc command with timeout. Returns markdown string or None on timeout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if result.stdout:
            print(f"Pandoc warnings: {stderr}")
            return result.stdout
        raise RuntimeError(
            f"Pandoc failed (exit {result.returncode}): {stderr or '(no error output)'}"
        )
    return result.stdout


def run_pandoc_latex(
    flattened_content: str,
    project_dir: Path,
    bib_files: list[Path],
    use_bib: bool,
) -> str:
    """Run pandoc on flattened LaTeX content, returning markdown."""
    if not shutil.which("pandoc"):
        raise RuntimeError(
            "pandoc is required but not found. Install from https://pandoc.org/"
        )

    PANDOC_TIMEOUT = 120

    tmp_tex = project_dir / "__flattened__.tex"
    tmp_tex.write_text(flattened_content, encoding="utf-8")

    try:
        base_cmd = [
            "pandoc",
            str(tmp_tex),
            "-f",
            "latex+latex_macros",
            "-t",
            "gfm+tex_math_dollars",
            "--wrap=none",
        ]

        bib_path: Path | None = None
        if use_bib:
            if bib_files:
                bib_path = bib_files[0]
            else:
                bib_path = _find_bib_from_tex(flattened_content, project_dir)

        if use_bib and not bib_path:
            print(
                "Warning: No .bib file found. Citations will pass through as raw LaTeX."
            )

        cmd = list(base_cmd)
        if bib_path:
            cmd.extend(["--citeproc", f"--bibliography={bib_path}"])

        result = _run_pandoc_cmd(cmd, project_dir, PANDOC_TIMEOUT)

        if result is None and bib_path:
            print(
                "Warning: Pandoc timed out with --citeproc. Retrying without citation processing..."
            )
            result = _run_pandoc_cmd(base_cmd, project_dir, PANDOC_TIMEOUT)

        if result is None:
            raise RuntimeError(f"Pandoc timed out after {PANDOC_TIMEOUT}s")

        return result
    finally:
        tmp_tex.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Stage 4: Post-processing
# ---------------------------------------------------------------------------


def convert_math_delimiters(md: str) -> str:
    """Convert GFM math syntax to Obsidian-compatible $...$ / $$...$$ syntax."""
    md = re.sub(
        r"```\s*math\s*\n(.*?)\n```",
        lambda m: "$$\n" + m.group(1) + "\n$$",
        md,
        flags=re.DOTALL,
    )
    md = re.sub(r"\$`([^`]*?)`\$", r"$\1$", md)
    return md


def strip_html_artifacts(md: str) -> str:
    """Remove HTML artifacts left by pandoc's GFM output."""
    md = re.sub(r"<div[^>]*>\s*\n?", "", md)
    md = re.sub(r"</div>\s*\n?", "", md)
    md = re.sub(r"<figure[^>]*>\s*\n?", "", md)
    md = re.sub(r"</figure>\s*\n?", "", md)
    md = re.sub(r"<figcaption>(.*?)</figcaption>", r"*\1*", md, flags=re.DOTALL)
    md = re.sub(r"<embed[^>]*/?>", "", md)
    md = re.sub(r"<img[^>]*/?>", "", md)
    md = re.sub(r"</?p>", "", md)
    md = re.sub(r"<br\s*/?>", "", md)
    md = re.sub(r'<a\s+href="[^"]*"[^>]*>([^<]*)</a>', r"\1", md)
    md = re.sub(r"</?span[^>]*>", "", md)
    return md


def strip_labels_and_refs(md: str) -> str:
    """Remove leftover LaTeX labels and refs from markdown."""
    md = re.sub(
        r"\\(?:label|ref|eqref|tag|cref|Cref|autoref)\{[^}]*\}", "", md
    )
    return md


# ---------------------------------------------------------------------------
# Stage 5: Figures
# ---------------------------------------------------------------------------


def convert_figures(
    ctx: InputContext,
    output_dir: Path,
    config: ConversionConfig,
) -> tuple[dict[str, str], list[str]]:
    """Convert figures to PNG. Returns (old_path -> new_path mapping, warnings)."""
    figures_dir = output_dir / config.image_dir
    figures_dir.mkdir(parents=True, exist_ok=True)
    path_map: dict[str, str] = {}
    warnings: list[str] = []
    has_gs = shutil.which("gs") is not None

    for idx, fig_path in enumerate(ctx.figure_files, 1):
        stem = re.sub(r"[^\w-]", "_", fig_path.stem)
        out_name = f"fig_{idx:02d}_{stem}.png"
        out_path = figures_dir / out_name
        rel_out = f"{config.image_dir}/{out_name}"

        rel_to_project = str(fig_path.relative_to(ctx.project_dir))
        path_map[rel_to_project] = rel_out
        path_map[fig_path.name] = rel_out
        path_map[fig_path.stem] = rel_out

        if fig_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            shutil.copy2(fig_path, out_path.with_suffix(fig_path.suffix))
            actual_name = f"fig_{idx:02d}_{stem}{fig_path.suffix.lower()}"
            actual_out = figures_dir / actual_name
            if out_path.with_suffix(fig_path.suffix) != actual_out:
                shutil.move(
                    str(out_path.with_suffix(fig_path.suffix)), str(actual_out)
                )
            rel_actual = f"{config.image_dir}/{actual_name}"
            path_map[rel_to_project] = rel_actual
            path_map[fig_path.name] = rel_actual
            path_map[fig_path.stem] = rel_actual

        elif fig_path.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(str(fig_path))
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                pix.save(str(out_path))
                doc.close()
            except Exception as e:
                warnings.append(f"Failed to convert {fig_path.name}: {e}")

        elif fig_path.suffix.lower() == ".eps":
            if has_gs:
                try:
                    subprocess.run(
                        [
                            "gs",
                            "-dBATCH",
                            "-dNOPAUSE",
                            "-dSAFER",
                            "-sDEVICE=pngalpha",
                            "-r300",
                            f"-sOutputFile={out_path}",
                            str(fig_path),
                        ],
                        capture_output=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    warnings.append(
                        f"Ghostscript failed for {fig_path.name}: {e}"
                    )
            else:
                warnings.append(
                    f"Skipping {fig_path.name}: Ghostscript (gs) required for EPS conversion"
                )

        elif fig_path.suffix.lower() == ".svg":
            shutil.copy2(fig_path, figures_dir / f"fig_{idx:02d}_{stem}.svg")
            rel_svg = f"{config.image_dir}/fig_{idx:02d}_{stem}.svg"
            path_map[rel_to_project] = rel_svg
            path_map[fig_path.name] = rel_svg
            path_map[fig_path.stem] = rel_svg

    return path_map, warnings


# ---------------------------------------------------------------------------
# Stage 6: Copy bib
# ---------------------------------------------------------------------------


def copy_bib(bib_files: list[Path], output_dir: Path) -> list[str]:
    """Copy .bib files to output directory."""
    copied = []
    for bib in bib_files:
        dst = output_dir / bib.name
        shutil.copy2(bib, dst)
        copied.append(str(dst))
    return copied


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def convert(
    source: str,
    output_dir: str,
    no_split: bool = False,
    no_figures: bool = False,
    image_dir: str = "figures",
    no_bib: bool = False,
    flatten_only: bool = False,
) -> None:
    """Convert LaTeX source to Obsidian-compatible Markdown.

    Args:
        source: arXiv ID (2301.12345), arXiv URL, .tex path, .zip (Overleaf), or .tar.gz.
        output_dir: Output directory for markdown files.
        no_split: Single output.md instead of per-section files.
        no_figures: Skip figure conversion/copying.
        image_dir: Figures subdirectory name.
        no_bib: Skip bibliography processing.
        flatten_only: Only produce flattened.tex, stop.
    """
    # fire may parse arXiv IDs like 2106.09685 as floats
    source = str(source)

    config = ConversionConfig(
        split=not no_split,
        figures=not no_figures,
        image_dir=image_dir,
        bib=not no_bib,
        flatten_only=flatten_only,
    )

    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    # Stage 1: Resolve input
    print(f"Resolving input: {source}")
    ctx = resolve_input(source)
    print(f"  Main .tex: {ctx.main_tex.name}")
    print(f"  Bib files: {[b.name for b in ctx.bib_files]}")
    print(f"  Figures: {len(ctx.figure_files)} found")

    try:
        # Stage 2: Flatten
        print("Flattening LaTeX...")
        flattened = flatten_latex(ctx.main_tex, ctx.project_dir)
        print(f"  Flattened: {len(flattened)} chars")

        if config.flatten_only:
            flat_out = out_path / "flattened.tex"
            flat_out.write_text(flattened, encoding="utf-8")
            print(f"Created: {flat_out}")
            return

        # Stage 3: Pandoc
        print("Running pandoc...")
        markdown = run_pandoc_latex(
            flattened, ctx.project_dir, ctx.bib_files, config.bib
        )
        print(f"  Pandoc output: {len(markdown)} chars")

        # Stage 4: Post-process
        print("Post-processing...")
        markdown = convert_math_delimiters(markdown)
        markdown = strip_html_artifacts(markdown)
        markdown = strip_labels_and_refs(markdown)
        markdown = clean_text(markdown)

        result = ConversionResult()

        # Convert figures
        figures_map: dict[str, str] = {}
        if config.figures and ctx.figure_files:
            print("Converting figures...")
            figures_map, fig_warnings = convert_figures(ctx, out_path, config)
            result.figure_count = len(ctx.figure_files)
            result.warnings.extend(fig_warnings)

        # Fix image paths
        if figures_map:
            markdown = fix_image_paths(markdown, figures_map)

        # Write output
        if config.split:
            sections = split_by_sections(markdown)
            for idx, (title, content) in enumerate(sections):
                slug = slugify(title)
                filename = f"{idx:02d}-{slug}.md"
                filepath = out_path / filename
                filepath.write_text(content.strip() + "\n", encoding="utf-8")
                result.files_created.append(str(filepath))
                print(f"  Created: {filename}")
        else:
            output_file = out_path / "output.md"
            output_file.write_text(markdown, encoding="utf-8")
            result.files_created.append(str(output_file))
            print("  Created: output.md")

        # Stage 5: Copy bib
        if config.bib and ctx.bib_files:
            copied = copy_bib(ctx.bib_files, out_path)
            result.files_created.extend(copied)
            print(f"  Copied bib: {[Path(c).name for c in copied]}")

        # Summary
        print(f"\nDone: {len(result.files_created)} files created")
        if result.figure_count:
            print(f"  Figures: {result.figure_count} processed")
        for w in result.warnings:
            print(f"  Warning: {w}")

    finally:
        if ctx.is_temp:
            shutil.rmtree(ctx.project_dir.parent, ignore_errors=True)
