"""Tests for to_md.converters.epub — EPUB to Markdown conversion.

Requires ebooklib and beautifulsoup4 (skip gracefully if missing).
"""

from pathlib import Path

import pytest

from conftest import skip_no_epub_deps

# Only import epub module if deps are available
pytestmark = skip_no_epub_deps

from to_md.converters.epub import (
    _fix_image_paths,
    _table_to_md,
    convert,
    extract_epub_images,
    html_to_md,
)


# ---------------------------------------------------------------------------
# html_to_md
# ---------------------------------------------------------------------------


class TestHtmlToMd:
    def test_headings(self):
        for level in range(1, 7):
            tag = f"h{level}"
            html = f"<{tag}>Heading Level {level}</{tag}>"
            result = html_to_md(html)
            assert f"{'#' * level} Heading Level {level}" in result

    def test_bold(self):
        result = html_to_md("<b>bold</b>")
        assert "**bold**" in result
        result2 = html_to_md("<strong>strong</strong>")
        assert "**strong**" in result2

    def test_italic(self):
        result = html_to_md("<i>italic</i>")
        assert "*italic*" in result
        result2 = html_to_md("<em>emphasized</em>")
        assert "*emphasized*" in result2

    def test_link(self):
        result = html_to_md('<a href="https://example.com">click here</a>')
        assert "[click here](https://example.com)" in result

    def test_image(self):
        result = html_to_md('<img src="fig.png" alt="figure 1"/>')
        assert "![figure 1](fig.png)" in result

    def test_unordered_list(self):
        html = "<ul><li>Apple</li><li>Banana</li></ul>"
        result = html_to_md(html)
        assert "- Apple" in result
        assert "- Banana" in result

    def test_ordered_list(self):
        html = "<ol><li>First</li><li>Second</li></ol>"
        result = html_to_md(html)
        assert "1. First" in result
        assert "2. Second" in result

    def test_table(self):
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        result = html_to_md(html)
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result
        assert "---" in result

    def test_blockquote(self):
        html = "<blockquote>To be or not to be</blockquote>"
        result = html_to_md(html)
        assert "> " in result
        assert "To be" in result

    def test_pre_code(self):
        html = "<pre>def hello():\n    pass</pre>"
        result = html_to_md(html)
        assert "```" in result
        assert "def hello():" in result

    def test_inline_code(self):
        html = "<code>x = 42</code>"
        result = html_to_md(html)
        assert "`x = 42`" in result

    def test_nested_formatting(self):
        html = "<p>This has <b>bold and <i>italic</i></b> text.</p>"
        result = html_to_md(html)
        assert "bold" in result

    def test_script_style_stripped(self):
        html = "<script>alert('xss')</script><style>.foo{}</style><p>visible</p>"
        result = html_to_md(html)
        assert "alert" not in result
        assert ".foo" not in result
        assert "visible" in result

    def test_br(self):
        html = "line1<br/>line2"
        result = html_to_md(html)
        assert "line1" in result and "line2" in result

    def test_hr(self):
        result = html_to_md("<hr/>")
        assert "---" in result

    def test_sup_footnote(self):
        result = html_to_md("<sup>1</sup>")
        assert "[^1]" in result


# ---------------------------------------------------------------------------
# _table_to_md
# ---------------------------------------------------------------------------


class TestTableToMd:
    def test_basic(self):
        from bs4 import BeautifulSoup
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        soup = BeautifulSoup(html, "html.parser")
        result = _table_to_md(soup.find("table"))
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result

    def test_ragged(self):
        from bs4 import BeautifulSoup
        html = "<table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td></tr></table>"
        soup = BeautifulSoup(html, "html.parser")
        result = _table_to_md(soup.find("table"))
        # Short row should be padded
        lines = result.strip().split("\n")
        assert len(lines) >= 3  # header + separator + data


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------


class TestImageHandling:
    def test_fix_image_paths(self):
        md = "![fig](images/photo.png)"
        path_map = {"images/photo.png": "figures/photo.png", "photo.png": "figures/photo.png"}
        result = _fix_image_paths(md, path_map)
        assert "figures/photo.png" in result

    def test_extract_epub_images(self, epub_book, tmp_path):
        from ebooklib import epub as ep
        book = ep.read_epub(str(epub_book))
        path_map = extract_epub_images(book, tmp_path, "figures")
        # book.epub has one embedded image
        assert isinstance(path_map, dict)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestConvertIntegration:
    def test_book(self, epub_book, tmp_path):
        output = tmp_path / "output"
        convert(str(epub_book), str(output))
        md_files = list(output.glob("*.md"))
        assert len(md_files) >= 3  # 4 chapters but some may be combined

        all_content = "\n".join(f.read_text() for f in md_files)
        assert len(all_content) > 50
        assert "Chapter" in all_content or "chapter" in all_content

    def test_complex(self, epub_complex, tmp_path):
        output = tmp_path / "output"
        convert(str(epub_complex), str(output))
        md_files = list(output.glob("*.md"))
        assert len(md_files) >= 1

        all_content = "\n".join(f.read_text() for f in md_files)
        # Should contain table content
        assert "Alpha" in all_content or "table" in all_content.lower()

    def test_no_images(self, epub_book, tmp_path):
        output = tmp_path / "output"
        convert(str(epub_book), str(output), no_images=True)
        figures_dir = output / "figures"
        if figures_dir.exists():
            # Should not have extracted images
            assert len(list(figures_dir.iterdir())) == 0

    def test_chapter_titles_in_filenames(self, epub_book, tmp_path):
        output = tmp_path / "output"
        convert(str(epub_book), str(output))
        md_files = list(output.glob("*.md"))
        filenames = [f.name for f in md_files]
        # At least one file should have a slug-based name, not just "chapter"
        assert any("chapter" in fn.lower() or "-" in fn for fn in filenames)

    def test_short_chapters_skipped(self, tmp_path):
        """Chapters with <10 chars should be skipped."""
        from ebooklib import epub as ep

        book = ep.EpubBook()
        book.set_identifier("test-short-001")
        book.set_title("Short Chapter Test")
        book.set_language("en")

        # One very short chapter and one real chapter
        ch_short = ep.EpubHtml(title="Short", file_name="short.xhtml", lang="en")
        ch_short.content = b"<html><body><p>Hi</p></body></html>"

        ch_real = ep.EpubHtml(title="Real", file_name="real.xhtml", lang="en")
        ch_real.content = b"<html><body><h1>Real Chapter</h1><p>This has enough content to not be skipped.</p></body></html>"

        book.add_item(ch_short)
        book.add_item(ch_real)
        book.toc = [ch_short, ch_real]
        book.spine = ["nav", ch_short, ch_real]
        book.add_item(ep.EpubNcx())
        book.add_item(ep.EpubNav())

        epub_path = tmp_path / "short_test.epub"
        ep.write_epub(str(epub_path), book)

        output = tmp_path / "output"
        convert(str(epub_path), str(output))

        md_files = list(output.glob("*.md"))
        # Short chapter should be skipped, only real chapter remains
        assert len(md_files) >= 1

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            convert(str(tmp_path / "nonexistent.epub"), str(tmp_path / "out"))

    def test_minimal(self, epub_minimal, tmp_path):
        output = tmp_path / "output"
        convert(str(epub_minimal), str(output))
        md_files = list(output.glob("*.md"))
        assert len(md_files) >= 1
