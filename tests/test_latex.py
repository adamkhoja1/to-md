"""Tests for to_md.converters.latex — LaTeX to Markdown conversion.

Unit tests for deterministic functions should pass.
Integration tests check structural properties (files created, content non-empty).
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from to_md.converters.latex import (
    ConversionConfig,
    InputContext,
    _detect_arxiv_id,
    _discover_figures,
    _find_main_tex,
    convert,
    convert_figures,
    convert_math_delimiters,
    flatten_latex,
    strip_html_artifacts,
    strip_labels_and_refs,
)

from conftest import skip_no_pandoc


# ---------------------------------------------------------------------------
# arXiv ID detection
# ---------------------------------------------------------------------------


class TestDetectArxivId:
    def test_plain_id(self):
        assert _detect_arxiv_id("2106.09685") == "2106.09685"

    def test_versioned(self):
        assert _detect_arxiv_id("2106.09685v2") == "2106.09685v2"

    def test_url_abs(self):
        assert _detect_arxiv_id("https://arxiv.org/abs/2106.09685") == "2106.09685"

    def test_url_pdf(self):
        assert _detect_arxiv_id("https://arxiv.org/pdf/2106.09685") == "2106.09685"

    def test_url_eprint(self):
        assert _detect_arxiv_id("https://arxiv.org/e-print/2301.12345") == "2301.12345"

    def test_not_arxiv(self):
        assert _detect_arxiv_id("hello") is None

    def test_regular_number(self):
        assert _detect_arxiv_id("42") is None

    def test_whitespace_stripped(self):
        assert _detect_arxiv_id("  2106.09685  ") == "2106.09685"


# ---------------------------------------------------------------------------
# find_main_tex
# ---------------------------------------------------------------------------


class TestFindMainTex:
    def test_single_tex(self, tmp_path):
        (tmp_path / "paper.tex").write_text("content")
        result = _find_main_tex(tmp_path)
        assert result.name == "paper.tex"

    def test_begin_document(self, tmp_path):
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")
        (tmp_path / "intro.tex").write_text(r"\section{Intro}")
        result = _find_main_tex(tmp_path)
        assert result.name == "main.tex"

    def test_ambiguous(self, tmp_path):
        (tmp_path / "a.tex").write_text(r"\begin{document}")
        (tmp_path / "b.tex").write_text(r"\begin{document}")
        with pytest.raises(ValueError, match="Multiple"):
            _find_main_tex(tmp_path)

    def test_none(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No .tex"):
            _find_main_tex(tmp_path)


# ---------------------------------------------------------------------------
# discover_figures
# ---------------------------------------------------------------------------


class TestDiscoverFigures:
    def test_finds_figures(self, tmp_path):
        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "img.png").write_bytes(b"\x89PNG")
        (fig_dir / "plot.jpg").write_bytes(b"\xff\xd8")
        (fig_dir / "diagram.svg").write_text("<svg/>")

        result = _discover_figures(tmp_path)
        names = {f.name for f in result}
        assert "img.png" in names
        assert "plot.jpg" in names
        assert "diagram.svg" in names

    def test_root_dir_figures(self, tmp_path):
        (tmp_path / "fig.png").write_bytes(b"\x89PNG")
        result = _discover_figures(tmp_path)
        assert any(f.name == "fig.png" for f in result)

    def test_no_figures(self, tmp_path):
        result = _discover_figures(tmp_path)
        assert result == []

    def test_multiple_dirs(self, tmp_path):
        for d in ["figures", "figs", "images"]:
            (tmp_path / d).mkdir()
            (tmp_path / d / f"{d}.png").write_bytes(b"\x89PNG")
        result = _discover_figures(tmp_path)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# flatten_latex
# ---------------------------------------------------------------------------


class TestFlattenLatex:
    def test_single_no_includes(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text(r"\section{Hello}")
        result = flatten_latex(tex, tmp_path)
        assert r"\section{Hello}" in result

    def test_with_input(self, latex_multi_file):
        main_tex = latex_multi_file / "main.tex"
        result = flatten_latex(main_tex, latex_multi_file)
        assert r"\section{Introduction}" in result
        assert r"\section{Methods}" in result

    def test_circular(self, latex_circular):
        a_tex = latex_circular / "a.tex"
        result = flatten_latex(a_tex, latex_circular)
        assert "Content from a" in result
        assert "Content from b" in result
        assert "WARNING: circular include" in result

    def test_missing_include(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text(r"\input{nonexistent}")
        result = flatten_latex(tex, tmp_path)
        assert "WARNING" in result
        assert "nonexistent" in result

    def test_no_extension(self, tmp_path):
        main = tmp_path / "main.tex"
        sub = tmp_path / "section.tex"
        main.write_text(r"\input{section}")
        sub.write_text("Section content")
        result = flatten_latex(main, tmp_path)
        assert "Section content" in result


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


class TestConvertMathDelimiters:
    def test_display_math(self):
        md = "```math\nx^2 + y^2 = z^2\n```"
        result = convert_math_delimiters(md)
        assert "$$" in result
        assert "x^2 + y^2 = z^2" in result
        assert "```" not in result

    def test_inline_math(self):
        md = "$`x + y`$"
        result = convert_math_delimiters(md)
        assert result == "$x + y$"

    def test_no_math(self):
        md = "Just plain text"
        assert convert_math_delimiters(md) == md


class TestStripHtmlArtifacts:
    def test_removes_div(self):
        assert "<div" not in strip_html_artifacts('<div class="foo">text</div>')

    def test_removes_figure(self):
        assert "<figure" not in strip_html_artifacts("<figure>content</figure>")

    def test_figcaption_to_italic(self):
        result = strip_html_artifacts("<figcaption>Caption text</figcaption>")
        assert "*Caption text*" in result

    def test_removes_br(self):
        assert "<br" not in strip_html_artifacts("text<br/>more")

    def test_removes_img(self):
        assert "<img" not in strip_html_artifacts('<img src="foo.png"/>')

    def test_removes_span(self):
        assert "<span" not in strip_html_artifacts('<span class="x">text</span>')

    def test_removes_embed(self):
        assert "<embed" not in strip_html_artifacts('<embed src="file.pdf"/>')

    def test_removes_links_keeps_text(self):
        result = strip_html_artifacts('<a href="http://example.com">link text</a>')
        assert "link text" in result
        assert "<a" not in result


class TestStripLabelsAndRefs:
    def test_label(self):
        assert r"\label" not in strip_labels_and_refs(r"text \label{eq:1} more")

    def test_ref(self):
        assert r"\ref" not in strip_labels_and_refs(r"see \ref{fig:1}")

    def test_eqref(self):
        assert r"\eqref" not in strip_labels_and_refs(r"equation \eqref{eq:main}")

    def test_cref(self):
        assert r"\cref" not in strip_labels_and_refs(r"see \cref{sec:intro}")

    def test_autoref(self):
        assert r"\autoref" not in strip_labels_and_refs(r"see \autoref{tab:1}")

    def test_tag(self):
        assert r"\tag" not in strip_labels_and_refs(r"x^2 \tag{1}")


# ---------------------------------------------------------------------------
# Figure conversion
# ---------------------------------------------------------------------------


class TestConvertFigures:
    def test_png_copied(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        fig_dir = project / "figures"
        fig_dir.mkdir()
        png = fig_dir / "test.png"
        # Create a real small PNG
        from conftest import _create_small_png
        _create_small_png(png)

        output = tmp_path / "output"
        output.mkdir()

        ctx = InputContext(
            project_dir=project,
            main_tex=project / "main.tex",
            figure_files=[png],
        )
        config = ConversionConfig()

        path_map, warnings = convert_figures(ctx, output, config)
        assert len(path_map) > 0
        assert (output / "figures").exists()

    def test_svg_copied(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        svg = project / "diagram.svg"
        svg.write_text("<svg></svg>")

        output = tmp_path / "output"
        output.mkdir()

        ctx = InputContext(
            project_dir=project,
            main_tex=project / "main.tex",
            figure_files=[svg],
        )
        config = ConversionConfig()

        path_map, warnings = convert_figures(ctx, output, config)
        assert any(".svg" in v for v in path_map.values())

    def test_eps_no_gs(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        eps = project / "plot.eps"
        eps.write_text("%!PS-Adobe")

        output = tmp_path / "output"
        output.mkdir()

        ctx = InputContext(
            project_dir=project,
            main_tex=project / "main.tex",
            figure_files=[eps],
        )
        config = ConversionConfig()

        with patch("to_md.converters.latex.shutil.which", return_value=None):
            path_map, warnings = convert_figures(ctx, output, config)

        assert any("Ghostscript" in w for w in warnings)

    def test_pdf_figure_rasterized(self, tmp_path):
        """PDF figures should be rasterized to PNG via fitz."""
        import fitz
        project = tmp_path / "project"
        project.mkdir()

        # Create a minimal PDF figure
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((10, 50), "Fig", fontsize=12)
        pdf_fig = project / "figure.pdf"
        doc.save(str(pdf_fig))
        doc.close()

        output = tmp_path / "output"
        output.mkdir()

        ctx = InputContext(
            project_dir=project,
            main_tex=project / "main.tex",
            figure_files=[pdf_fig],
        )
        config = ConversionConfig()

        path_map, warnings = convert_figures(ctx, output, config)
        assert any(".png" in v for v in path_map.values())
        assert not warnings


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestConvertIntegration:
    @skip_no_pandoc
    def test_simple_paper(self, latex_simple_paper, tmp_path):
        """Full pipeline on simple_paper fixture."""
        output = tmp_path / "output"
        convert(str(latex_simple_paper / "paper.tex"), str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) > 0

        all_content = "\n".join(f.read_text() for f in md_files)
        assert len(all_content) > 100
        # Check structural properties
        assert "Introduction" in all_content or "introduction" in all_content
        assert "Conclusion" in all_content or "conclusion" in all_content

    @skip_no_pandoc
    def test_multifile(self, latex_multi_file, tmp_path):
        """Full pipeline on multi_file fixture with includes."""
        output = tmp_path / "output"
        convert(str(latex_multi_file / "main.tex"), str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) > 0

        all_content = "\n".join(f.read_text() for f in md_files)
        # Content from both included files should be present
        assert "Introduction" in all_content or "introduction" in all_content
        assert "Methods" in all_content or "pipeline" in all_content.lower()

    @skip_no_pandoc
    def test_zip(self, latex_overleaf_zip, tmp_path):
        """Full pipeline on overleaf.zip fixture."""
        output = tmp_path / "output"
        convert(str(latex_overleaf_zip), str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) > 0

    @skip_no_pandoc
    def test_no_split(self, latex_simple_paper, tmp_path):
        """--no-split produces single output.md."""
        output = tmp_path / "output"
        convert(str(latex_simple_paper / "paper.tex"), str(output), no_split=True)

        assert (output / "output.md").exists()
        md_files = list(output.glob("*.md"))
        assert len(md_files) == 1

    @skip_no_pandoc
    def test_flatten_only(self, latex_simple_paper, tmp_path):
        """--flatten-only produces flattened.tex, stops."""
        output = tmp_path / "output"
        convert(str(latex_simple_paper / "paper.tex"), str(output), flatten_only=True)

        assert (output / "flattened.tex").exists()
        md_files = list(output.glob("*.md"))
        assert len(md_files) == 0

    @pytest.mark.network
    def test_arxiv_download(self, tmp_path):
        """Downloads a real arXiv paper (attention is all you need)."""
        output = tmp_path / "output"
        convert("1706.03762", str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) > 0
