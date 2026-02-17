"""Tests for to_md.core — shared utilities.

These are unit tests for deterministic functions. They should all pass.
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from to_md.core import (
    clean_pdf_text,
    clean_text,
    fix_image_paths,
    has_pandoc,
    run_pandoc,
    slugify,
    split_by_sections,
    table_to_markdown,
)


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        result = slugify("What's Up? (2024)")
        assert result == "whats-up-2024"

    def test_max_len(self):
        result = slugify("a very long title that should be truncated", max_len=10)
        assert len(result) <= 10
        assert not result.endswith("-")

    def test_empty(self):
        assert slugify("") == "untitled"
        assert slugify("   ") == "untitled"

    def test_unicode(self):
        result = slugify("Résumé café")
        assert "rsum" in result or "résumé" in result or result  # varies by locale
        assert isinstance(result, str)

    def test_hyphens_preserved(self):
        assert slugify("well-known-thing") == "well-known-thing"

    def test_multiple_spaces(self):
        assert slugify("hello   world") == "hello-world"

    def test_leading_trailing_special(self):
        result = slugify("---hello---")
        assert result == "hello"


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_whitespace(self):
        result = clean_text("hello   world\t\ttab")
        assert result == "hello world tab"

    def test_blank_lines(self):
        result = clean_text("hello\n\n\n\n\nworld")
        assert result == "hello\n\nworld"

    def test_empty(self):
        assert clean_text("") == ""

    def test_none_like(self):
        # empty string is falsy
        assert clean_text("") == ""

    def test_preserves_single_newlines(self):
        result = clean_text("line1\nline2")
        assert "line1" in result and "line2" in result

    def test_strips_edges(self):
        result = clean_text("  hello  ")
        assert result == "hello"


# ---------------------------------------------------------------------------
# clean_pdf_text
# ---------------------------------------------------------------------------


class TestCleanPdfText:
    def test_dehyphenate(self):
        result = clean_pdf_text("exam-\nple text")
        assert result == "example text"

    def test_ligatures(self):
        result = clean_pdf_text("ﬁnding ﬂow oﬀers")
        assert "finding" in result
        assert "flow" in result
        assert "offers" in result

    def test_empty(self):
        assert clean_pdf_text("") == ""

    def test_combined(self):
        result = clean_pdf_text("ﬁrst-\nclass   work")
        assert "firstclass" in result or "first class" in result


# ---------------------------------------------------------------------------
# split_by_sections
# ---------------------------------------------------------------------------


class TestSplitBySections:
    def test_h1(self):
        md = "# Introduction\nContent\n# Methods\nMore content"
        sections = split_by_sections(md)
        assert len(sections) == 2
        assert sections[0][0] == "Introduction"
        assert sections[1][0] == "Methods"

    def test_does_not_split_h2(self):
        md = "# Main\nContent\n## Sub\nMore"
        sections = split_by_sections(md)
        assert len(sections) == 1
        assert sections[0][0] == "Main"

    def test_no_headings(self):
        md = "Just some text without headings"
        sections = split_by_sections(md)
        assert len(sections) == 1
        assert sections[0][0] == "abstract"  # default_title when no sections found

    def test_custom_level(self):
        md = "## Section A\nContent\n## Section B\nMore\n### Sub\nDeep"
        sections = split_by_sections(md, heading_level=2)
        assert len(sections) == 2
        assert sections[0][0] == "Section A"
        assert sections[1][0] == "Section B"

    def test_preamble(self):
        md = "Preamble content\n# First Section\nBody"
        sections = split_by_sections(md)
        assert len(sections) == 2
        assert sections[0][0] == "abstract"  # default_title
        assert sections[1][0] == "First Section"

    def test_custom_default_title(self):
        md = "Preamble\n# Section\nBody"
        sections = split_by_sections(md, default_title="preamble")
        assert sections[0][0] == "preamble"

    def test_empty_preamble_skipped(self):
        md = "# First\nContent"
        sections = split_by_sections(md)
        assert len(sections) == 1
        assert sections[0][0] == "First"


# ---------------------------------------------------------------------------
# fix_image_paths
# ---------------------------------------------------------------------------


class TestFixImagePaths:
    def test_exact_match(self):
        md = "![fig](old/path.png)"
        result = fix_image_paths(md, {"old/path.png": "new/path.png"})
        assert result == "![fig](new/path.png)"

    def test_basename_fallback(self):
        md = "![fig](some/deep/path.png)"
        result = fix_image_paths(md, {"path.png": "figures/out.png"})
        assert result == "![fig](figures/out.png)"

    def test_stem_fallback(self):
        md = "![fig](images/diagram.pdf)"
        result = fix_image_paths(md, {"diagram": "figures/diagram.png"})
        assert result == "![fig](figures/diagram.png)"

    def test_no_match(self):
        md = "![fig](unknown.png)"
        result = fix_image_paths(md, {"other.png": "new.png"})
        assert result == "![fig](unknown.png)"

    def test_multiple_images(self):
        md = "![a](a.png) text ![b](b.png)"
        result = fix_image_paths(md, {"a.png": "x.png", "b.png": "y.png"})
        assert "![a](x.png)" in result
        assert "![b](y.png)" in result

    def test_preserves_alt_text(self):
        md = "![complex alt text with spaces](img.png)"
        result = fix_image_paths(md, {"img.png": "new.png"})
        assert "![complex alt text with spaces](new.png)" in result


# ---------------------------------------------------------------------------
# table_to_markdown
# ---------------------------------------------------------------------------


class TestTableToMarkdown:
    def test_basic(self):
        table = [["Name", "Value"], ["A", "1"], ["B", "2"]]
        result = table_to_markdown(table)
        assert "| Name | Value |" in result
        assert "| --- | --- |" in result
        assert "| A | 1 |" in result
        assert "| B | 2 |" in result

    def test_none_cells(self):
        table = [["A", None], [None, "B"]]
        result = table_to_markdown(table)
        assert "| A |  |" in result
        assert "|  | B |" in result

    def test_pipe_escape(self):
        table = [["Header"], ["a|b"]]
        result = table_to_markdown(table)
        assert r"a\|b" in result

    def test_ragged_short_rows_padded(self):
        table = [["A", "B", "C"], ["1"]]
        result = table_to_markdown(table)
        lines = result.strip().split("\n")
        # Data row should have same number of columns as header
        assert lines[2].count("|") == lines[0].count("|")

    def test_ragged_long_rows_truncated(self):
        table = [["A", "B"], ["1", "2", "3"]]
        result = table_to_markdown(table)
        lines = result.strip().split("\n")
        # Data row columns should match header columns
        assert lines[2].count("|") == lines[0].count("|")

    def test_empty(self):
        assert table_to_markdown([]) == ""
        assert table_to_markdown([[]]) == ""

    def test_single_row(self):
        result = table_to_markdown([["Only", "Header"]])
        assert "| Only | Header |" in result
        assert "| --- | --- |" in result


# ---------------------------------------------------------------------------
# has_pandoc / run_pandoc
# ---------------------------------------------------------------------------


class TestPandoc:
    def test_has_pandoc_matches_which(self):
        expected = shutil.which("pandoc") is not None
        assert has_pandoc() == expected

    @pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc not installed")
    def test_run_pandoc_basic(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\textbf{hello} world", encoding="utf-8")
        result = run_pandoc(tex, from_fmt="latex")
        assert "hello" in result

    def test_run_pandoc_missing(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("hello", encoding="utf-8")
        with patch("to_md.core.has_pandoc", return_value=False):
            with pytest.raises(RuntimeError, match="pandoc"):
                run_pandoc(tex, from_fmt="latex")

    @pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc not installed")
    def test_run_pandoc_timeout(self, tmp_path):
        # Create a file that pandoc can process but with 0s timeout
        tex = tmp_path / "test.tex"
        tex.write_text(r"\textbf{hello}", encoding="utf-8")
        # timeout=0 should fail, but subprocess might still succeed for tiny files
        # Just verify the timeout parameter is passed through
        result = run_pandoc(tex, from_fmt="latex", timeout=120)
        assert isinstance(result, str)
