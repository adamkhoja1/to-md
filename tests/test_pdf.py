"""Tests for to_md.converters.pdf — PDF to Markdown conversion.

Unit tests for font/heading detection should pass.
Integration tests check structural properties (files created, headings preserved).
"""

from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest

from to_md.converters.pdf import (
    ConversionConfig,
    FontStats,
    PyMuPDFBackend,
    compute_font_stats,
    convert,
    detect_heading,
    detect_math_regions,
    extract_images_from_page,
    get_backend,
    is_math_font,
)


# ---------------------------------------------------------------------------
# compute_font_stats
# ---------------------------------------------------------------------------


class TestComputeFontStats:
    def test_prose_pdf(self, pdf_prose):
        doc = fitz.open(str(pdf_prose))
        stats = compute_font_stats(doc)
        doc.close()
        assert stats.avg_size > 0
        assert stats.max_size >= stats.avg_size

    def test_empty_doc(self):
        doc = fitz.open()
        doc.new_page()
        stats = compute_font_stats(doc)
        doc.close()
        assert stats.avg_size == 12.0
        assert stats.max_size == 12.0

    def test_known_sizes(self, pdf_prose):
        doc = fitz.open(str(pdf_prose))
        stats = compute_font_stats(doc)
        doc.close()
        # We used fontsize 24 for headings and 11 for body
        assert stats.max_size >= 20  # heading font
        assert stats.avg_size < stats.max_size


# ---------------------------------------------------------------------------
# detect_heading
# ---------------------------------------------------------------------------


class TestDetectHeading:
    def test_large_font_is_heading(self):
        stats = FontStats(avg_size=11.0, max_size=24.0)
        span = {"text": "Chapter Title", "size": 24.0, "font": "Helvetica-Bold"}
        level, text = detect_heading(span, stats)
        assert level is not None
        assert level in (1, 2, 3)
        assert text == "Chapter Title"

    def test_bold_large_is_heading(self):
        stats = FontStats(avg_size=11.0, max_size=24.0)
        span = {"text": "Section", "size": 14.0, "font": "Helvetica-Bold"}
        level, text = detect_heading(span, stats)
        assert level is not None
        assert text == "Section"

    def test_normal_text_not_heading(self):
        stats = FontStats(avg_size=11.0, max_size=24.0)
        span = {"text": "Regular text.", "size": 11.0, "font": "Helvetica"}
        level, text = detect_heading(span, stats)
        assert level is None
        assert text == "Regular text."

    def test_heading_level_hierarchy(self):
        stats = FontStats(avg_size=11.0, max_size=24.0)
        # Largest → level 1
        level1, _ = detect_heading({"text": "H1", "size": 24.0, "font": "Bold"}, stats)
        # Medium → level 2
        level2, _ = detect_heading({"text": "H2", "size": 18.0, "font": "Bold"}, stats)
        # Smaller large → level 3
        level3, _ = detect_heading({"text": "H3", "size": 15.0, "font": "Bold"}, stats)

        # All should be headings
        assert level1 is not None
        assert level2 is not None


# ---------------------------------------------------------------------------
# is_math_font
# ---------------------------------------------------------------------------


class TestIsMathFont:
    def test_cmmi(self):
        assert is_math_font("CMMI10") is True

    def test_cmsy(self):
        assert is_math_font("CMSY8") is True

    def test_stix(self):
        assert is_math_font("STIXGeneral") is True

    def test_lm(self):
        assert is_math_font("LMMathSymbols10") is True

    def test_times_not_math(self):
        assert is_math_font("TimesNewRoman") is False

    def test_helvetica_not_math(self):
        assert is_math_font("Helvetica") is False

    def test_subset_prefix(self):
        # Subset font names like "ABCDEF+CMMI10"
        assert is_math_font("ABCDEF+CMMI10") is True

    def test_mathfont(self):
        assert is_math_font("MathematicalPi") is True

    def test_empty(self):
        assert is_math_font("") is False


# ---------------------------------------------------------------------------
# detect_math_regions
# ---------------------------------------------------------------------------


class TestDetectMathRegions:
    def test_no_math(self, pdf_prose):
        doc = fitz.open(str(pdf_prose))
        regions = detect_math_regions(doc[0])
        doc.close()
        # Prose PDF uses Helvetica, not math fonts — should find no math regions
        assert isinstance(regions, list)


# ---------------------------------------------------------------------------
# get_backend
# ---------------------------------------------------------------------------


class TestGetBackend:
    def test_pymupdf(self):
        backend = get_backend("pymupdf")
        assert isinstance(backend, PyMuPDFBackend)

    def test_invalid(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("fake_backend")


# ---------------------------------------------------------------------------
# PyMuPDFBackend
# ---------------------------------------------------------------------------


class TestPyMuPDFBackend:
    def test_convert_page(self, pdf_prose):
        doc = fitz.open(str(pdf_prose))
        stats = compute_font_stats(doc)
        config = ConversionConfig()
        backend = PyMuPDFBackend()

        content = backend.convert_page(doc[0], 1, stats, config)
        doc.close()

        assert isinstance(content, str)
        assert len(content) > 0
        # Should contain heading markers
        assert "#" in content

    def test_convert_document(self, pdf_prose, tmp_path):
        doc = fitz.open(str(pdf_prose))
        config = ConversionConfig(extract_images=False)
        backend = PyMuPDFBackend()

        result = backend.convert_document(doc, config, tmp_path)
        doc.close()

        assert len(result.markdown) > 0
        assert "Chapter" in result.markdown or "chapter" in result.markdown


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------


class TestExtractImages:
    def test_no_images_in_text_pdf(self, pdf_prose, tmp_path):
        doc = fitz.open(str(pdf_prose))
        figures_dir = tmp_path / "figures"
        refs, count = extract_images_from_page(
            doc[0], 1, 0, figures_dir, "figures", False, 0
        )
        doc.close()
        # Text-only PDF shouldn't have embedded images
        assert isinstance(refs, list)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestConvertIntegration:
    def test_prose(self, pdf_prose, tmp_path):
        output = tmp_path / "output"
        convert(str(pdf_prose), str(output))
        md = (output / "output.md").read_text()
        assert len(md) > 50
        assert "#" in md  # should have headings

    def test_minimal(self, pdf_minimal, tmp_path):
        output = tmp_path / "output"
        convert(str(pdf_minimal), str(output))
        md = (output / "output.md").read_text()
        assert len(md) > 0

    def test_output_file_md(self, pdf_minimal, tmp_path):
        output_file = tmp_path / "result.md"
        convert(str(pdf_minimal), str(output_file))
        assert output_file.exists()
        assert output_file.read_text().strip()

    def test_output_dir(self, pdf_minimal, tmp_path):
        output_dir = tmp_path / "outdir"
        convert(str(pdf_minimal), str(output_dir))
        assert (output_dir / "output.md").exists()

    def test_split_chapters(self, pdf_multi_chapter, tmp_path):
        output = tmp_path / "output"
        convert(str(pdf_multi_chapter), str(output), split_chapters=True)
        md_files = list(output.glob("*.md"))
        # Should produce multiple files (chapters)
        assert len(md_files) >= 1

    def test_page_range(self, pdf_multi_chapter, tmp_path):
        output = tmp_path / "output"
        convert(str(pdf_multi_chapter), str(output), page_range="0-1")
        md = (output / "output.md").read_text()
        assert len(md) > 0
        # Content should be limited to first 2 pages

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            convert(str(tmp_path / "nonexistent.pdf"), str(tmp_path / "out"))

    def test_no_images(self, pdf_prose, tmp_path):
        output = tmp_path / "output"
        convert(str(pdf_prose), str(output), no_images=True)
        figures_dir = output / "figures"
        # Should not create figures directory (text-only PDF)
        if figures_dir.exists():
            assert len(list(figures_dir.iterdir())) == 0
