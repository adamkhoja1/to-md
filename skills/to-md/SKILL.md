---
name: to-md
description: >-
  Convert documents to clean Obsidian-compatible markdown. Supports LaTeX (.tex, arXiv), PDF, EPUB,
  DOCX, URLs, and Google Slides text exports. Use when the user wants to convert any document to
  markdown — e.g. "convert this paper", "arxiv to markdown", "convert this PDF", "save this webpage
  as markdown", "convert docx", "epub to markdown", "convert slides to markdown", "format this slide
  export".
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(uv:*), Bash(git:*), Bash(gh:*), AskUserQuestion
---

# Document to Markdown Conversion

Convert documents to well-structured, Obsidian-compatible markdown with support for:
- **LaTeX** — arXiv papers, Overleaf exports, .tex files (math, citations, figures)
- **PDF** — multiple backends, image extraction, chapter splitting
- **EPUB** — chapter splitting, image extraction
- **DOCX** — single or batch conversion, image extraction
- **URL** — web article extraction with optional images
- **Slides** — Google Slides plain-text (.txt) exports → structured markdown (LLM-driven, no script)
- **AI OCR** — math equation images to LaTeX

## Prerequisites Check

**Run this before any conversion.** Stop and help the user fix any failures.

```bash
# 1. Project exists?
test -d ~/Projects/to-md/src/to_md && echo "OK: project found" || echo "FAIL: project not found"

# 2. Dependencies installed?
uv run --project ~/Projects/to-md python -c "import to_md" 2>&1 && echo "OK: deps installed" || echo "FAIL: run 'cd ~/Projects/to-md && uv sync'"

# 3. Pandoc available?
which pandoc && echo "OK: pandoc found" || echo "WARN: pandoc not found (needed for latex/docx)"
```

**If project not found:** `git clone <repo-url> ~/Projects/to-md && cd ~/Projects/to-md && uv sync`

**If deps not installed:** `cd ~/Projects/to-md && uv sync --all-extras`

## Decision Flowchart

```
1. Is LaTeX source (.tex) available?
   → YES: Use `to_md latex` (best quality for academic papers)

2. Is it an arXiv paper?
   → YES with source available: Use `to_md latex` with arXiv ID
   → YES but source unavailable (404): Use `to_md pdf` instead

3. Is the input an EPUB?
   → YES: Use `to_md epub`

4. Is the input a DOCX?
   → YES: Use `to_md docx`

5. Is it a web page / URL?
   → YES: Use `to_md url`

6. Is it a Google Slides plain-text export (.txt)?
   → YES: Interpret into markdown per references/slides.md (LLM task, no script)

7. Is it a PDF?
   → Check page count and choose backend (see PDF section below)

8. Are there scanned math equation images?
   → YES: Use `to_md ocr`
```

## Invocation Pattern

```bash
uv run --project ~/Projects/to-md python -m to_md <format> SOURCE OUTPUT [OPTIONS]
```

## LaTeX Conversion

Convert LaTeX source to markdown with math preservation, citation formatting, and figure conversion.

**Why prefer LaTeX source over PDF?** Converting from source preserves math exactly, maintains document structure, and produces far cleaner output than any PDF extraction approach.

### Examples

```bash
# arXiv paper by ID
uv run --project ~/Projects/to-md python -m to_md latex 2301.12345 /tmp/output/

# arXiv paper by URL
uv run --project ~/Projects/to-md python -m to_md latex "https://arxiv.org/abs/2301.12345" /tmp/output/

# Local .tex file
uv run --project ~/Projects/to-md python -m to_md latex paper.tex /tmp/output/

# Overleaf export (.zip)
uv run --project ~/Projects/to-md python -m to_md latex project.zip /tmp/output/

# Single file output (no splitting)
uv run --project ~/Projects/to-md python -m to_md latex paper.tex /tmp/output/ --no-split

# Flatten only (debug)
uv run --project ~/Projects/to-md python -m to_md latex paper.tex /tmp/output/ --flatten-only
```

### LaTeX Options

| Flag | Default | Description |
|------|---------|-------------|
| `--no-split` | `False` | Single `output.md` instead of per-section files |
| `--no-figures` | `False` | Skip figure conversion/copying |
| `--image-dir` | `figures` | Figures subdirectory name |
| `--no-bib` | `False` | Skip bibliography processing |
| `--flatten-only` | `False` | Only produce `flattened.tex`, stop before pandoc |

### LaTeX Cleanup Pass

After conversion, review the output for:
1. **Math rendering** — Check `$...$` and `$$...$$` blocks render correctly
2. **Unexpanded macros** — Search for remaining `\` commands pandoc didn't expand
3. **TikZ diagrams** — Replace with text descriptions (can't rasterize without full LaTeX toolchain)
4. **Citation formatting** — Verify `(Author Year)` citations rendered correctly
5. **Figure references** — Check `![](figures/...)` paths point to actual files
6. **Cross-references** — `\ref{}`, `\eqref{}` are stripped; add back important numbering if needed

## PDF Conversion

**IMPORTANT: The agent must never transcribe equations itself. Always delegate to the scripts.**

### Backend Selection

| Scenario | Action |
|----------|--------|
| Short docs (<100 pages) | Use marker. No need to ask. |
| Medium docs (100-300 pages) | **ASK the user.** Marker: ~15-40 min, best quality. PyMuPDF: seconds, adequate for simple prose. |
| Long docs (300+ pages) | **ALWAYS ask.** Marker: ~1-2 hours. For 700+ pages, chunk via `--page-range`. |
| Math-heavy PDF | Use `--backend marker --use-llm` or `--backend surya` |
| Scanned equations | Use `to_md ocr` |

### Examples

```bash
# PDF with Marker (recommended)
uv run --project ~/Projects/to-md --with marker-pdf python -m to_md pdf textbook.pdf output/ --backend marker

# PDF with PyMuPDF (fast fallback)
uv run --project ~/Projects/to-md python -m to_md pdf textbook.pdf output/

# PDF with Marker + LLM
uv run --project ~/Projects/to-md --with marker-pdf python -m to_md pdf textbook.pdf output/ --backend marker --use-llm

# PDF with Surya hybrid (math OCR)
uv run --project ~/Projects/to-md --with surya-ocr --with Pillow python -m to_md pdf textbook.pdf output/ --backend surya

# Split by chapters
uv run --project ~/Projects/to-md python -m to_md pdf textbook.pdf output/ --split-chapters

# Page range
uv run --project ~/Projects/to-md python -m to_md pdf textbook.pdf output/ --page-range 45-55
```

### PDF Options

| Flag | Description |
|------|-------------|
| `--backend marker` | **Recommended.** ML-based layout, tables, header/footer removal |
| `--backend pymupdf` | Fast fallback. Raw text extraction with font heuristics |
| `--backend surya` | Hybrid: PyMuPDF for prose, Surya OCR for math regions |
| `--use-llm` | Enable LLM-assisted conversion (marker backend only) |
| `--page-range START-END` | Convert specific pages (0-indexed, inclusive) |
| `--split-chapters` | Split into separate files at H1 headings |
| `--no-images` | Skip image extraction |
| `--image-dir NAME` | Custom figures directory name (default: `figures`) |

### Backend Comparison

| Backend | Speed | Quality | Best For | Extra Deps |
|---------|-------|---------|----------|------------|
| `marker` | ~5-10 min/50pp | **Best** | Most documents | marker-pdf |
| `marker --use-llm` | Slower | **Best** (math) | Math-heavy PDFs | marker-pdf + API key |
| `pymupdf` | Seconds | Basic | Simple prose, quick previews | (included) |
| `surya` | Similar to marker | Good (math) | Math OCR hybrid | surya-ocr, Pillow |

### QA Workspace & Fast Baseline

- **Lay down a fast PyMuPDF baseline first.** Before or alongside a slow marker/surya run, convert with the default PyMuPDF backend into a `workspace/` subfolder of the output dir, chapter-split. It costs seconds, gives an early readable draft, and serves as the default scratch area for all QA artifacts (logs, findings, fix scripts) — keep them in `workspace/` so the final output dir stays clean.

```bash
uv run --project ~/Projects/to-md python -m to_md pdf textbook.pdf output/workspace/ --split-chapters
```

- **Use the baseline as a sanity checker.** For PDFs with an embedded text layer the PyMuPDF text is digit-exact, so when QA'ing a marker/LLM conversion, diff it against the baseline per chapter (numbers, equations, wording) to catch silent OCR corruption that a single backend won't reveal. This diff is the standard converter-independent cross-check that `references/qa.md` requires for ML-backed conversions.

## EPUB Conversion

```bash
uv run --project ~/Projects/to-md python -m to_md epub book.epub output/
uv run --project ~/Projects/to-md python -m to_md epub book.epub output/ --no-images
```

| Flag | Description |
|------|-------------|
| `--no-images` | Skip image extraction |
| `--image-dir NAME` | Custom figures directory (default: `figures`) |

## DOCX Conversion

```bash
# Single file
uv run --project ~/Projects/to-md python -m to_md docx document.docx

# With output directory
uv run --project ~/Projects/to-md python -m to_md docx document.docx --output-dir output/

# Batch conversion
uv run --project ~/Projects/to-md python -m to_md docx "docs/*.docx"

# Strip images instead of extracting them
uv run --project ~/Projects/to-md python -m to_md docx document.docx --output-dir output/ --no-images
```

Uses pandoc if available (better output quality), falls back to mammoth + markdownify. Images are
extracted to a `figures/` directory by default; pass `--no-images` to strip them. In batch mode,
extracted images are prefixed with the source filename so they don't collide in a shared `figures/`.

| Argument | Description |
|----------|-------------|
| `source` | Path to a `.docx` file or glob pattern |
| `--output-dir` | Optional output directory (default: same as source) |
| `--no-images` | Strip images instead of extracting them |
| `--image-dir` | Custom figures directory name (default: `figures`) |

**See also:** for Word **comments** (preserved inline as CriticMarkup) or policy/CX **debate-card**
formatting (underline/highlight markup), use the standalone `docx-to-markdown` skill — to_md
intentionally keeps docx conversion minimal and does not handle those.

## URL Conversion

```bash
# Simple conversion
uv run --project ~/Projects/to-md python -m to_md url "https://example.com/article"

# With images
uv run --project ~/Projects/to-md python -m to_md url "https://example.com/article" --images

# Split by sections
uv run --project ~/Projects/to-md python -m to_md url "https://docs.example.com/guide" --split

# Custom output
uv run --project ~/Projects/to-md python -m to_md url "https://example.com/article" -o article.md
```

| Flag | Description |
|------|-------------|
| `-o, --output` | Custom output file (.md) or directory |
| `--images` | Download images to `figures/` directory |
| `--split` | Split into separate files at H1/H2 headings |
| `--image-dir` | Custom figures directory name (default: `figures`) |

When cleaning up scraped articles, always start from the scraped output and make targeted edits. Never rewrite the material wholesale.

## Slides Conversion (.txt)

Convert Google Slides "Download as Plain Text" exports into structured markdown.

**This is an LLM interpretation task — there is no script and no `to_md` subcommand.** The text export
strips all formatting, so slide boundaries, heading hierarchy, bullet nesting, and tables must be
inferred from context. **Read `references/slides.md` (in this skill directory) for the full heuristics
before converting.** In brief:

1. Read the entire `.txt` first; understand the deck's arc before converting anything.
2. Segment into slides on blank-line boundaries; the first line is the presentation title (`#`).
3. Classify each block — section divider (`##`), slide title (`###`), bullet, sub-bullet, table,
   quote, figure reference — and emit the matching markdown.
4. Infer sub-bullet hierarchy from specificity / "e.g." / category→instance signals.
5. **Preserve all content — never summarize or drop slides.**

Save output as `[original-filename].md` next to the source (or wherever the user requests).

## AI OCR (Math Equations)

For scanned equations or images of math that no backend can handle:

```bash
uv run --project ~/Projects/to-md python -m to_md ocr image1.png image2.png
uv run --project ~/Projects/to-md python -m to_md ocr image1.png --output equations.tex --yes
```

- Prompts user with cost estimate before running (~$0.005 per equation image)
- Use `--yes` to skip confirmation
- Use `--output file.tex` to save to file

## Quality Assurance

QA is format-independent — it operates on the markdown output. Full protocol, triage rules,
and templates: **`references/qa.md`**. Output formatting rules: **`references/styleguide.md`**.

Ask the user once, up front, which tier they want:

| Tier | Cost | Exit criteria |
|------|------|---------------|
| **T0 Lint** (default) | Near-zero | Deterministic checks clean; note what wasn't checked |
| **T1 Standard** | Modest | T0 + sanity-check invariants vs. source + light sampled adversarial text review; no known meaning-changing errors |
| **T2 Audit** (opt-in) | Expensive | T1 + fresh-context reviewer agents iterated until dry; quantified coverage statement |

**Floor the tier by converter risk** (not just document importance): ML/OCR backends
(`marker`/`surya`/`--use-llm`/`ocr`) → minimum **T1** with a mandatory `references/baseline_diff.py`
cross-check; scanned PDFs with no text layer → **T2**. Deterministic text paths may default lower.

Hard rules at every tier:

- **Never edit `~/Projects/to-md` during a conversion.** A converter bug confirmed by a *failing
  repro* → file a deduped GitHub issue (`gh`), self-contained enough to reproduce from the issue
  alone, with a high-level fix suggestion. Never edit the converter yourself.
- **Every content fix is a transcription from the original** (cite page/location) — never a
  reconstruction from memory.
- **Document-specific fix code lives in the output's `workspace/`.** `git init` there before
  the first scripted bulk edit: commit pristine output first, then one commit per fix (script
  + effects). Dry-run fix scripts on a sample before bulk application.
- **Measure before fixing** — count an error class before choosing a strategy; widespread
  judgment-heavy classes signal rework (backend/flags), not manual repair.
- **End with a residual-risk note**: what was checked, what wasn't, what's still open.

## Output Structure

```
output_dir/
├── 00-abstract.md       (or 00-frontmatter.md for PDFs)
├── 01-introduction.md
├── 02-related-work.md
├── ...
├── references.bib       (LaTeX only)
└── figures/
    ├── fig_01_diagram.png
    └── ...
```

Files follow the naming convention `{idx:02d}-{slugify(title)}.md`.

## Dependencies

Core dependencies (installed with `uv sync`): fire, pydantic, pymupdf, requests

Optional dependencies (install with `uv sync --extra <name>`):

| Extra | Packages | Needed For |
|-------|----------|------------|
| `url` | trafilatura | URL conversion |
| `docx` | mammoth, markdownify | DOCX fallback (without pandoc) |
| `epub` | ebooklib, beautifulsoup4 | EPUB conversion |
| `marker` | marker-pdf | ML-based PDF backend |
| `surya` | surya-ocr, Pillow | Math OCR hybrid backend |
| `ocr` | anthropic | AI equation OCR |
| `all` | url + docx + epub | All common extras |

### External Tools

- **pandoc** (required for latex/docx): `brew install pandoc`
- **ghostscript** (optional, for EPS figures): `brew install ghostscript`

## Limitations

- **TikZ diagrams** cannot be rasterized without a full LaTeX toolchain. Describe textually in cleanup pass.
- **Complex custom macros** beyond pandoc's `+latex_macros` appear as raw LaTeX.
- **JavaScript-rendered sites** may return incomplete content from URL extraction.
- **Marker on 700+ page PDFs** may crash from tensor size limits. Use `--page-range` to chunk.
