"""Test fixtures: programmatic generation of realistic test data.

All generated data is cached in tests/data/ (gitignored) so it's created once per session.
No network required — all fixtures are generated locally.
"""

import shutil
import struct
import zipfile
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest

DATA_DIR = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# Skip markers for optional dependencies
# ---------------------------------------------------------------------------

has_pandoc = shutil.which("pandoc") is not None
has_gs = shutil.which("gs") is not None

try:
    import trafilatura  # noqa: F401
    has_trafilatura = True
except ImportError:
    has_trafilatura = False

try:
    import mammoth  # noqa: F401
    has_mammoth = True
except ImportError:
    has_mammoth = False

try:
    import ebooklib  # noqa: F401
    from bs4 import BeautifulSoup  # noqa: F401
    has_epub_deps = True
except ImportError:
    has_epub_deps = False

skip_no_pandoc = pytest.mark.skipif(not has_pandoc, reason="pandoc not installed")
skip_no_gs = pytest.mark.skipif(not has_gs, reason="ghostscript not installed")
skip_no_trafilatura = pytest.mark.skipif(not has_trafilatura, reason="trafilatura not installed")
skip_no_mammoth = pytest.mark.skipif(not has_mammoth, reason="mammoth not installed")
skip_no_epub_deps = pytest.mark.skipif(not has_epub_deps, reason="ebooklib/bs4 not installed")


# ---------------------------------------------------------------------------
# LaTeX fixtures
# ---------------------------------------------------------------------------


def _create_small_png(path: Path) -> None:
    """Create a minimal valid 1x1 white PNG file."""
    # IHDR + IDAT for 1x1 white pixel
    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        import zlib
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    import zlib
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    raw_data = b"\x00\xff\xff\xff"  # filter byte + white pixel
    idat = zlib.compress(raw_data)

    path.write_bytes(
        signature
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


@pytest.fixture(scope="session")
def latex_simple_paper() -> Path:
    """Simple LaTeX paper with abstract, sections, math, citations, figure ref."""
    d = DATA_DIR / "latex" / "simple_paper"
    if d.exists():
        return d
    d.mkdir(parents=True)

    (d / "paper.tex").write_text(r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{natbib}

\title{A Simple Test Paper}
\author{Test Author}

\begin{document}
\maketitle

\begin{abstract}
This paper tests the LaTeX to Markdown conversion pipeline. We study the function $f(x) = x^2$ and its properties.
\end{abstract}

\section{Introduction}
Machine learning has revolutionized many fields \citep{goodfellow2016deep}. Consider the equation:
$$E = mc^2$$

We also examine inline math like $\alpha + \beta = \gamma$.

\section{Methods}
Our method uses the following loss function:
\begin{equation}
\mathcal{L} = \sum_{i=1}^{N} (y_i - \hat{y}_i)^2
\end{equation}

\begin{figure}[h]
\centering
\includegraphics[width=0.5\textwidth]{figures/diagram}
\caption{A test diagram showing the architecture.}
\label{fig:diagram}
\end{figure}

See Figure~\ref{fig:diagram} for details.

\section{Conclusion}
We have demonstrated the conversion pipeline works correctly.

\bibliographystyle{plainnat}
\bibliography{refs}

\end{document}
""", encoding="utf-8")

    (d / "refs.bib").write_text(r"""@book{goodfellow2016deep,
  title={Deep Learning},
  author={Goodfellow, Ian and Bengio, Yoshua and Courville, Aaron},
  year={2016},
  publisher={MIT Press}
}
""", encoding="utf-8")

    fig_dir = d / "figures"
    fig_dir.mkdir()
    _create_small_png(fig_dir / "diagram.png")

    return d


@pytest.fixture(scope="session")
def latex_multi_file() -> Path:
    r"""Multi-file LaTeX project with \input directives."""
    d = DATA_DIR / "latex" / "multi_file"
    if d.exists():
        return d
    d.mkdir(parents=True)

    (d / "main.tex").write_text(r"""\documentclass{article}
\begin{document}

\title{Multi-file Paper}
\maketitle

\input{intro}
\input{methods}

\bibliography{refs}
\end{document}
""", encoding="utf-8")

    (d / "intro.tex").write_text(r"""\section{Introduction}
This is the introduction section. We study the problem of converting LaTeX to Markdown.
The field has seen significant progress in recent years.
""", encoding="utf-8")

    (d / "methods.tex").write_text(r"""\section{Methods}
We use a pipeline approach:
\begin{enumerate}
\item Flatten includes
\item Run pandoc
\item Post-process
\end{enumerate}

The key equation is $y = mx + b$.
""", encoding="utf-8")

    (d / "refs.bib").write_text(r"""@article{test2024,
  title={Testing},
  author={Test},
  year={2024},
  journal={Journal of Testing}
}
""", encoding="utf-8")

    return d


@pytest.fixture(scope="session")
def latex_circular() -> Path:
    """LaTeX files with circular includes: a.tex -> b.tex -> a.tex."""
    d = DATA_DIR / "latex" / "circular"
    if d.exists():
        return d
    d.mkdir(parents=True)

    (d / "a.tex").write_text(r"""\documentclass{article}
\begin{document}
Content from a.
\input{b}
\end{document}
""", encoding="utf-8")

    (d / "b.tex").write_text(r"""Content from b.
\input{a}
""", encoding="utf-8")

    return d


@pytest.fixture(scope="session")
def latex_heavy_math() -> Path:
    """LaTeX with dense math environments."""
    d = DATA_DIR / "latex" / "heavy_math"
    if d.exists():
        return d
    d.mkdir(parents=True)

    (d / "paper.tex").write_text(r"""\documentclass{article}
\usepackage{amsmath,amsthm,amssymb}

\newcommand{\R}{\mathbb{R}}
\newcommand{\norm}[1]{\left\|#1\right\|}

\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}

\begin{document}

\section{Mathematical Framework}

\begin{theorem}
For all $x \in \R^n$, the following inequality holds:
\begin{equation}
\norm{Ax} \leq \norm{A} \cdot \norm{x}
\end{equation}
\end{theorem}

\begin{proof}
By the Cauchy-Schwarz inequality, we have:
\begin{align}
\norm{Ax}^2 &= \sum_{i=1}^{m} \left( \sum_{j=1}^{n} a_{ij} x_j \right)^2 \\
&\leq \sum_{i=1}^{m} \left( \sum_{j=1}^{n} a_{ij}^2 \right) \left( \sum_{j=1}^{n} x_j^2 \right) \\
&= \norm{A}_F^2 \cdot \norm{x}^2
\end{align}
Taking the square root gives the result.
\end{proof}

\begin{lemma}
If $A$ is symmetric positive definite, then all eigenvalues are positive.
\end{lemma}

\end{document}
""", encoding="utf-8")

    return d


@pytest.fixture(scope="session")
def latex_overleaf_zip(latex_multi_file: Path) -> Path:
    """ZIP archive of multi_file project (simulates Overleaf export)."""
    zip_path = DATA_DIR / "latex" / "overleaf.zip"
    if zip_path.exists():
        return zip_path
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in latex_multi_file.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(latex_multi_file))

    return zip_path


# ---------------------------------------------------------------------------
# PDF fixtures (generated with PyMuPDF)
# ---------------------------------------------------------------------------


def _insert_text(page: fitz.Page, point: tuple[float, float], text: str,
                 fontsize: float = 11, fontname: str = "helv",
                 bold: bool = False) -> float:
    """Insert text and return the y position after it."""
    fn = fontname
    if bold and fontname == "helv":
        fn = "hebo"
    elif "italic" in fontname.lower():
        fn = "heit"
    tw = page.insert_text(point, text, fontsize=fontsize, fontname=fn)
    return point[1] + tw  # approximate next y


@pytest.fixture(scope="session")
def pdf_prose() -> Path:
    """3-page PDF with H1/H2 headings at larger font sizes, bold/italic."""
    p = DATA_DIR / "pdf" / "prose.pdf"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    body = (
        "Machine learning is a subset of artificial intelligence that focuses on "
        "building systems that learn from data. These systems improve their performance "
        "on a specific task over time without being explicitly programmed."
    )

    for page_num in range(3):
        page = doc.new_page(width=612, height=792)
        y = 72

        if page_num == 0:
            page.insert_text((72, y), "Chapter One: Introduction", fontsize=24, fontname="hebo")
            y += 40
            page.insert_text((72, y), "Background and Motivation", fontsize=18, fontname="hebo")
            y += 30
        elif page_num == 1:
            page.insert_text((72, y), "Chapter Two: Methods", fontsize=24, fontname="hebo")
            y += 40
            page.insert_text((72, y), "Data Collection", fontsize=18, fontname="hebo")
            y += 30
        else:
            page.insert_text((72, y), "Chapter Three: Results", fontsize=24, fontname="hebo")
            y += 40

        # Body text in multiple blocks
        for i in range(5):
            page.insert_text((72, y), body, fontsize=11, fontname="helv")
            y += 60

    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture(scope="session")
def pdf_with_tables() -> Path:
    """PDF containing a structured table."""
    p = DATA_DIR / "pdf" / "with_tables.pdf"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 72

    page.insert_text((72, y), "Table of Results", fontsize=20, fontname="hebo")
    y += 40

    # Draw a simple table with text
    headers = ["Model", "Accuracy", "F1 Score"]
    rows = [
        ["Baseline", "0.82", "0.79"],
        ["Our Method", "0.91", "0.88"],
        ["SOTA", "0.89", "0.86"],
    ]

    x_positions = [72, 200, 350]
    for i, h in enumerate(headers):
        page.insert_text((x_positions[i], y), h, fontsize=11, fontname="hebo")
    y += 20
    page.draw_line((72, y - 5), (500, y - 5))
    for row in rows:
        for i, cell in enumerate(row):
            page.insert_text((x_positions[i], y), cell, fontsize=11, fontname="helv")
        y += 18

    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture(scope="session")
def pdf_multi_chapter() -> Path:
    """5+ page PDF with clear H1 chapter breaks."""
    p = DATA_DIR / "pdf" / "multi_chapter.pdf"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    chapters = ["Abstract", "Introduction", "Related Work", "Methods", "Results", "Conclusion"]
    body_text = "This section contains the main discussion of the topic at hand. " * 3

    for title in chapters:
        page = doc.new_page(width=612, height=792)
        y = 72
        page.insert_text((72, y), title, fontsize=24, fontname="hebo")
        y += 40
        page.insert_text((72, y), body_text, fontsize=11, fontname="helv")

    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture(scope="session")
def pdf_math_fonts() -> Path:
    """PDF with text using math font names (CMMI, CMSY) for is_math_font testing."""
    p = DATA_DIR / "pdf" / "math_fonts.pdf"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    # We can't easily embed CM fonts in PyMuPDF-generated PDFs, but we can
    # test the utility functions directly. Create a minimal PDF for integration.
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "The equation f(x) = ax^2 + bx + c has roots.", fontsize=11, fontname="helv")
    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture(scope="session")
def pdf_minimal() -> Path:
    """Single page, uniform font, no structure."""
    p = DATA_DIR / "pdf" / "minimal.pdf"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Just some plain text with no headings or structure.", fontsize=11, fontname="helv")
    doc.save(str(p))
    doc.close()
    return p


# ---------------------------------------------------------------------------
# EPUB fixtures (generated with ebooklib)
# ---------------------------------------------------------------------------


def _make_epub_chapter(title: str, body_html: str, filename: str) -> "epub.EpubHtml":
    """Helper to create an EPUB chapter."""
    from ebooklib import epub as ep
    ch = ep.EpubHtml(title=title, file_name=filename, lang="en")
    ch.content = f"<html><body><h1>{title}</h1>{body_html}</body></html>".encode("utf-8")
    return ch


@pytest.fixture(scope="session")
def epub_book() -> Path:
    """4-chapter EPUB with headings, paragraphs, formatting, list, and image."""
    p = DATA_DIR / "epub" / "book.epub"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    if not has_epub_deps:
        pytest.skip("ebooklib not installed")

    from ebooklib import epub as ep

    book = ep.EpubBook()
    book.set_identifier("test-book-001")
    book.set_title("Test Book")
    book.set_language("en")
    book.add_author("Test Author")

    # Create a small PNG image to embed
    img_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50  # minimal (invalid but tests path)
    img_path = DATA_DIR / "epub" / "_tmp_img.png"
    _create_small_png(img_path)
    img_item = ep.EpubImage()
    img_item.file_name = "images/figure1.png"
    img_item.media_type = "image/png"
    img_item.content = img_path.read_bytes()
    book.add_item(img_item)
    img_path.unlink()

    chapters = []
    ch1 = _make_epub_chapter("Chapter 1: Getting Started",
        "<p>This is the <b>first</b> chapter with <i>italic</i> text.</p>"
        "<p>It has multiple paragraphs of content.</p>",
        "ch01.xhtml")
    chapters.append(ch1)

    ch2 = _make_epub_chapter("Chapter 2: Core Concepts",
        "<p>The second chapter covers key ideas.</p>"
        "<ul><li>Point one</li><li>Point two</li><li>Point three</li></ul>",
        "ch02.xhtml")
    chapters.append(ch2)

    ch3 = _make_epub_chapter("Chapter 3: Images",
        '<p>Here is a diagram:</p><img src="../images/figure1.png" alt="Figure 1"/>',
        "ch03.xhtml")
    chapters.append(ch3)

    ch4 = _make_epub_chapter("Chapter 4: Conclusion",
        "<p>In conclusion, this book covers the essentials.</p>"
        "<p>Thank you for reading.</p>",
        "ch04.xhtml")
    chapters.append(ch4)

    for ch in chapters:
        book.add_item(ch)

    book.toc = chapters
    book.spine = ["nav"] + chapters
    book.add_item(ep.EpubNcx())
    book.add_item(ep.EpubNav())

    ep.write_epub(str(p), book)
    return p


@pytest.fixture(scope="session")
def epub_complex() -> Path:
    """EPUB with tables, blockquotes, code, nested lists, footnotes."""
    p = DATA_DIR / "epub" / "complex.epub"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    if not has_epub_deps:
        pytest.skip("ebooklib not installed")

    from ebooklib import epub as ep

    book = ep.EpubBook()
    book.set_identifier("test-complex-001")
    book.set_title("Complex Test Book")
    book.set_language("en")

    ch1 = _make_epub_chapter("Tables and Code",
        "<table><tr><th>Name</th><th>Value</th></tr>"
        "<tr><td>Alpha</td><td>1</td></tr>"
        "<tr><td>Beta</td><td>2</td></tr></table>"
        "<pre>def hello():\n    print('world')</pre>",
        "ch01.xhtml")

    ch2 = _make_epub_chapter("Quotes and Footnotes",
        "<blockquote>To be or not to be, that is the question.</blockquote>"
        "<p>As noted<sup>1</sup>, this is important.</p>"
        "<p>With <b>nested <i>formatting</i></b> in text.</p>",
        "ch02.xhtml")

    for ch in [ch1, ch2]:
        book.add_item(ch)

    book.toc = [ch1, ch2]
    book.spine = ["nav", ch1, ch2]
    book.add_item(ep.EpubNcx())
    book.add_item(ep.EpubNav())

    ep.write_epub(str(p), book)
    return p


@pytest.fixture(scope="session")
def epub_minimal() -> Path:
    """Single chapter EPUB, no images."""
    p = DATA_DIR / "epub" / "minimal.epub"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    if not has_epub_deps:
        pytest.skip("ebooklib not installed")

    from ebooklib import epub as ep

    book = ep.EpubBook()
    book.set_identifier("test-minimal-001")
    book.set_title("Minimal Book")
    book.set_language("en")

    ch = _make_epub_chapter("Only Chapter",
        "<p>This is the only chapter in this minimal book.</p>",
        "ch01.xhtml")
    book.add_item(ch)
    book.toc = [ch]
    book.spine = ["nav", ch]
    book.add_item(ep.EpubNcx())
    book.add_item(ep.EpubNav())

    ep.write_epub(str(p), book)
    return p


# ---------------------------------------------------------------------------
# DOCX fixtures (generated with pandoc if available)
# ---------------------------------------------------------------------------


def _make_docx_via_pandoc(md_content: str, output_path: Path) -> bool:
    """Generate a .docx from markdown via pandoc. Returns True on success."""
    if not has_pandoc:
        return False
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(md_content)
        md_path = f.name
    try:
        subprocess.run(
            ["pandoc", md_path, "-f", "gfm", "-t", "docx", "-o", str(output_path)],
            capture_output=True, check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        Path(md_path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def docx_simple() -> Path:
    """Simple DOCX with headings, paragraphs, bold, italic."""
    p = DATA_DIR / "docx" / "simple.docx"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    md = """# Introduction

This is a **simple** document with *italic* text.

## Background

The background section provides context for the work.

## Methods

We used a standard approach to solve the problem.
"""
    if not _make_docx_via_pandoc(md, p):
        pytest.skip("pandoc not available to generate docx fixtures")
    return p


@pytest.fixture(scope="session")
def docx_with_tables() -> Path:
    """DOCX with a markdown table."""
    p = DATA_DIR / "docx" / "with_tables.docx"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    md = """# Results

| Model | Accuracy | F1 |
|-------|----------|----|
| A     | 0.85     | 0.82 |
| B     | 0.91     | 0.89 |

The results show that Model B is better.
"""
    if not _make_docx_via_pandoc(md, p):
        pytest.skip("pandoc not available to generate docx fixtures")
    return p


@pytest.fixture(scope="session")
def docx_batch() -> Path:
    """Directory with two .docx files for batch conversion testing."""
    d = DATA_DIR / "docx" / "batch"
    if d.exists():
        return d
    d.mkdir(parents=True, exist_ok=True)

    for name, content in [("a", "# Document A\n\nContent of document A."),
                          ("b", "# Document B\n\nContent of document B.")]:
        p = d / f"{name}.docx"
        if not _make_docx_via_pandoc(content, p):
            pytest.skip("pandoc not available to generate docx fixtures")

    return d


# ---------------------------------------------------------------------------
# HTML fixtures (static files, no generation needed)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def html_article() -> Path:
    """Full HTML page with nav, header, main, article, footer, aside."""
    p = DATA_DIR / "html" / "article.html"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test Article: Machine Learning Fundamentals</title>
    <meta name="author" content="Test Author">
    <meta name="description" content="An overview of machine learning fundamentals">
</head>
<body>
    <nav><a href="/">Home</a> | <a href="/about">About</a></nav>
    <header><h1>Machine Learning Fundamentals</h1></header>
    <main>
        <article>
            <h2>Introduction</h2>
            <p>Machine learning is a branch of <strong>artificial intelligence</strong>
            that focuses on building systems that learn from <em>data</em>.</p>

            <h2>Key Concepts</h2>
            <ul>
                <li>Supervised Learning</li>
                <li>Unsupervised Learning</li>
                <li>Reinforcement Learning</li>
            </ul>

            <h2>Applications</h2>
            <p>ML is used in many domains including:</p>
            <ol>
                <li>Computer Vision</li>
                <li>Natural Language Processing</li>
                <li>Recommendation Systems</li>
            </ol>

            <img src="images/diagram.png" alt="ML Overview">

            <h2>Conclusion</h2>
            <p>Machine learning continues to advance rapidly.</p>
        </article>
    </main>
    <aside><p>Related: Deep Learning, Neural Networks</p></aside>
    <footer><p>Copyright 2024 Test Author</p></footer>
</body>
</html>""", encoding="utf-8")

    return p


@pytest.fixture(scope="session")
def html_minimal() -> Path:
    """Minimal HTML page."""
    p = DATA_DIR / "html" / "minimal.html"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text("<html><body><p>Hello</p></body></html>", encoding="utf-8")
    return p


@pytest.fixture(scope="session")
def html_no_title() -> Path:
    """HTML with content but no title."""
    p = DATA_DIR / "html" / "no_title.html"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text("""<html><body>
<h2>Some Section</h2>
<p>Content without any title element in the head.</p>
</body></html>""", encoding="utf-8")
    return p


@pytest.fixture(scope="session")
def html_with_images() -> Path:
    """HTML with various image src patterns."""
    p = DATA_DIR / "html" / "with_images.html"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text("""<!DOCTYPE html>
<html>
<head><title>Page With Images</title></head>
<body>
<h1>Images Test</h1>
<img src="images/local.png" alt="Local image">
<img src="https://example.com/remote.jpg" alt="Remote image">
<img src="data:image/png;base64,iVBORw0KGgo=" alt="Data URI image">
<p>Some text between images.</p>
</body>
</html>""", encoding="utf-8")

    return p
