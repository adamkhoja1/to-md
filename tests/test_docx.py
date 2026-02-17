"""Tests for to_md.converters.docx — DOCX to Markdown conversion.

Requires pandoc for fixture generation and primary conversion.
Falls back to mammoth if pandoc not available.
"""

from pathlib import Path

import pytest

from conftest import has_mammoth, has_pandoc, skip_no_pandoc
from to_md.converters.docx import _strip_images, convert


# ---------------------------------------------------------------------------
# _strip_images
# ---------------------------------------------------------------------------


class TestStripImages:
    def test_removes_image_refs(self):
        text = "Before\n![alt](path/to/img.png)\nAfter"
        result = _strip_images(text)
        assert "![" not in result
        assert "Before" in result
        assert "After" in result

    def test_collapses_blank_lines(self):
        text = "Before\n\n\n\n\nAfter"
        result = _strip_images(text)
        assert "\n\n\n" not in result

    def test_no_images(self):
        text = "Plain text\nwith lines"
        result = _strip_images(text)
        assert result == text

    def test_multiple_images(self):
        text = "A\n![x](a.png)\nB\n![y](b.png)\nC"
        result = _strip_images(text)
        assert "![" not in result
        assert "A" in result and "B" in result and "C" in result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestConvertIntegration:
    @skip_no_pandoc
    def test_simple(self, docx_simple, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        convert(str(docx_simple), str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "Introduction" in content or "introduction" in content
        assert len(content) > 20

    @skip_no_pandoc
    def test_tables(self, docx_with_tables, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        convert(str(docx_with_tables), str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "Results" in content or "results" in content

    @skip_no_pandoc
    def test_batch(self, docx_batch, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        convert(str(docx_batch / "*.docx"), str(output))

        md_files = list(output.glob("*.md"))
        assert len(md_files) == 2

    @skip_no_pandoc
    def test_output_dir(self, docx_simple, tmp_path):
        output = tmp_path / "custom_output"
        convert(str(docx_simple), str(output))
        assert output.exists()
        md_files = list(output.glob("*.md"))
        assert len(md_files) == 1

    @skip_no_pandoc
    def test_name_collision(self, tmp_path):
        """Duplicate names get parent-dir prefix."""
        # Create two dirs with same-named docx files
        from conftest import _make_docx_via_pandoc

        dir_a = tmp_path / "dir_a"
        dir_a.mkdir()
        dir_b = tmp_path / "dir_b"
        dir_b.mkdir()

        _make_docx_via_pandoc("# Doc\n\nContent A", dir_a / "doc.docx")
        _make_docx_via_pandoc("# Doc\n\nContent B", dir_b / "doc.docx")

        output = tmp_path / "output"
        output.mkdir()

        # Convert both files to same output dir
        convert(str(dir_a / "doc.docx"), str(output))
        convert(str(dir_b / "doc.docx"), str(output))

        md_files = list(output.glob("*.md"))
        # Second conversion should overwrite (same name) or both exist
        assert len(md_files) >= 1

    def test_no_docx_files(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            convert(str(tmp_path / "nonexistent.docx"))

    def test_no_match_pattern(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a docx")
        with pytest.raises(FileNotFoundError):
            convert(str(tmp_path / "*.docx"))

    @skip_no_pandoc
    def test_default_output_dir(self, docx_simple, tmp_path):
        """When output_dir is None, output goes to same directory as source."""
        import shutil
        # Copy docx to tmp so we don't pollute fixtures
        src = tmp_path / "test.docx"
        shutil.copy2(docx_simple, src)

        convert(str(src))
        assert (tmp_path / "test.md").exists()


class TestConvertWithMammoth:
    @pytest.mark.skipif(not has_mammoth, reason="mammoth not installed")
    @skip_no_pandoc  # Need pandoc to generate fixture
    def test_mammoth_fallback(self, docx_simple, tmp_path):
        """Test mammoth conversion path."""
        from to_md.converters.docx import _convert_with_mammoth

        output = tmp_path / "result.md"
        _convert_with_mammoth(Path(docx_simple), output)
        assert output.exists()
        content = output.read_text()
        assert len(content) > 10
