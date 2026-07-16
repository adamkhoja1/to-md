"""Tests for to_md.converters.url — URL to Markdown conversion.

Unit tests for utility functions use local fixtures.
Integration tests monkeypatch network calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from conftest import skip_no_trafilatura

# Conditionally import — many tests need trafilatura
try:
    from to_md.converters.url import (
        convert,
        dedup_image_tails,
        download_image,
        extract_images_from_markdown,
        extract_title,
        split_by_headings,
    )
    _has_url_module = True
except ImportError:
    _has_url_module = False

pytestmark = pytest.mark.skipif(not _has_url_module, reason="url converter deps not available")


# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    @skip_no_trafilatura
    def test_from_html(self, html_article):
        html = html_article.read_text()
        title = extract_title(html, "https://example.com/article")
        # Should extract "Test Article: Machine Learning Fundamentals" from <title>
        assert "Machine Learning" in title or len(title) > 5

    @skip_no_trafilatura
    def test_fallback_url(self, html_no_title):
        html = html_no_title.read_text()
        title = extract_title(html, "https://example.com/my-article")
        # Should fall back to URL path
        assert isinstance(title, str)
        assert len(title) > 0

    @skip_no_trafilatura
    def test_untitled(self, html_minimal):
        html = html_minimal.read_text()
        title = extract_title(html, "https://example.com/")
        # Root URL with no title might → "Untitled" or something from the page
        assert isinstance(title, str)
        assert len(title) > 0

    @skip_no_trafilatura
    def test_utf8_bytes_no_mojibake(self):
        """extract_title accepts raw bytes and decodes UTF-8 punctuation correctly."""
        raw = (
            "<html><head><title>A galaxy that doesn’t spin</title></head>"
            "<body><p>x</p></body></html>"
        ).encode("utf-8")
        title = extract_title(raw, "https://example.com/x")
        assert "â" not in title  # no Latin-1 mojibake ('â')
        assert "doesn’t spin" in title


# ---------------------------------------------------------------------------
# split_by_headings
# ---------------------------------------------------------------------------


class TestSplitByHeadings:
    def test_h1_h2(self):
        md = "# Section One\nContent\n## Section Two\nMore content"
        sections = split_by_headings(md, "Title")
        assert len(sections) >= 2

    def test_no_headings(self):
        md = "Just plain text without any headings at all."
        sections = split_by_headings(md, "My Title")
        assert len(sections) == 1
        assert sections[0][0] == "My Title"

    def test_preamble(self):
        md = "Preamble text here.\n\n# First Section\nContent"
        sections = split_by_headings(md, "Doc Title")
        assert len(sections) >= 2
        assert sections[0][0] == "Doc Title"

    def test_only_h1(self):
        md = "# A\nText A\n# B\nText B\n# C\nText C"
        sections = split_by_headings(md, "Title")
        assert len(sections) == 3

    def test_preserves_content(self):
        md = "# Intro\nSome important content.\n## Details\nMore details here."
        sections = split_by_headings(md, "Title")
        all_content = " ".join(s[1] for s in sections)
        assert "important content" in all_content
        assert "More details" in all_content


# ---------------------------------------------------------------------------
# download_image
# ---------------------------------------------------------------------------


class TestDownloadImage:
    def test_success(self, tmp_path):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"\x89PNG\r\n\x1a\n"
        mock_response.raise_for_status = MagicMock()

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            filename = download_image("https://example.com/img.png", tmp_path, 1)

        assert filename is not None
        assert filename.endswith(".png")
        assert (tmp_path / filename).exists()

    def test_failure_returns_none(self, tmp_path):
        with patch("to_md.converters.url.requests.get", side_effect=Exception("Network error")):
            result = download_image("https://example.com/bad.png", tmp_path, 1)

        assert result is None

    def test_jpg_content_type(self, tmp_path):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.content = b"\xff\xd8\xff"
        mock_response.raise_for_status = MagicMock()

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            filename = download_image("https://example.com/photo.jpg", tmp_path, 1)

        assert filename is not None
        assert filename.endswith(".jpg")


# ---------------------------------------------------------------------------
# dedup_image_tails
# ---------------------------------------------------------------------------


class TestDedupImageTails:
    """Guard against trafilatura 2.1.0's image-tail double emission.

    The duplicated shape is: an embed line carrying trailing text, followed by
    a paragraph that repeats that text (both copies come from one lxml tail).
    """

    def test_exact_duplicate_stripped(self):
        md = "![](http://x/a.jpg) They decided to rewrite it.\n\nThey decided to rewrite it.\n\nNext para."
        result = dedup_image_tails(md)
        assert result.count("They decided to rewrite it.") == 1
        assert "![](http://x/a.jpg)" in result.split("\n")[0]
        assert result.split("\n")[0] == "![](http://x/a.jpg)"

    def test_fragment_prefix_stripped(self):
        # Embed-line copy is a bare fragment; paragraph copy carries the full
        # sentence with inline formatting (the "The old mantra" case).
        md = (
            "![](http://x/b.jpg) The old mantra\n\n"
            "The old mantra *build one to throw away* is dangerous.\n"
        )
        result = dedup_image_tails(md)
        assert result.count("The old mantra") == 1
        assert "*build one to throw away*" in result

    def test_no_duplicate_unchanged(self):
        # Fixed-trafilatura shape: tail only on the embed line, next paragraph
        # unrelated. The guard must be a no-op.
        md = "![](http://x/c.jpg) A caption-like sentence.\n\nCompletely different paragraph."
        assert dedup_image_tails(md) == md

    def test_bare_embed_unchanged(self):
        md = "Intro para.\n\n![alt text](http://x/d.jpg)\n\nNext para."
        assert dedup_image_tails(md) == md

    def test_embed_at_end_unchanged(self):
        md = "Some text.\n\n![](http://x/e.jpg) trailing words"
        assert dedup_image_tails(md) == md

    def test_multiple_images_mixed(self):
        md = (
            "![](http://x/1.jpg) Duplicated one.\n\nDuplicated one.\n\n"
            "![](http://x/2.jpg) Kept caption.\n\nUnrelated paragraph.\n"
        )
        result = dedup_image_tails(md)
        assert result.count("Duplicated one.") == 1
        assert "![](http://x/2.jpg) Kept caption." in result

    def test_whitespace_normalized_match(self):
        # The paragraph copy may differ from the fragment in whitespace only.
        md = "![](http://x/f.jpg) two  words\n\ntwo words and more.\n"
        result = dedup_image_tails(md)
        assert result.split("\n")[0] == "![](http://x/f.jpg)"


# ---------------------------------------------------------------------------
# extract_images_from_markdown
# ---------------------------------------------------------------------------


class TestExtractImagesFromMarkdown:
    def test_data_uri_stripped(self, tmp_path):
        md = "![](data:image/png;base64,abc123)"
        result = extract_images_from_markdown(md, "https://example.com", tmp_path, "figures")
        assert "data:" not in result

    def test_relative_url_resolved(self, tmp_path):
        md = "![alt](images/photo.png)"

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"\x89PNG"
        mock_response.raise_for_status = MagicMock()

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            result = extract_images_from_markdown(md, "https://example.com/page", tmp_path, "figures")

        assert "figures/" in result

    def test_absolute_url(self, tmp_path):
        md = "![alt](https://example.com/img.png)"

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"\x89PNG"
        mock_response.raise_for_status = MagicMock()

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            result = extract_images_from_markdown(md, "https://example.com", tmp_path, "figures")

        assert "figures/" in result


# ---------------------------------------------------------------------------
# Integration tests (monkeypatched)
# ---------------------------------------------------------------------------


class TestConvertIntegration:
    @skip_no_trafilatura
    def test_article(self, html_article, tmp_path):
        """Full pipeline on local article.html via monkeypatch."""
        html_content = html_article.read_text()

        mock_response = MagicMock()
        mock_response.content = html_content.encode("utf-8")
        mock_response.raise_for_status = MagicMock()

        output = tmp_path / "result.md"

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            convert("https://example.com/article", output=str(output))

        assert output.exists()
        content = output.read_text()
        assert len(content) > 50

    @skip_no_trafilatura
    def test_split(self, html_article, tmp_path):
        """--split produces numbered files."""
        html_content = html_article.read_text()

        mock_response = MagicMock()
        mock_response.content = html_content.encode("utf-8")
        mock_response.raise_for_status = MagicMock()

        output_dir = tmp_path / "output"

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            convert("https://example.com/article", output=str(output_dir), split=True)

        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1

    @skip_no_trafilatura
    def test_no_output_auto_filename(self, html_article, tmp_path, monkeypatch):
        """Auto-generates filename from title slug."""
        html_content = html_article.read_text()

        mock_response = MagicMock()
        mock_response.content = html_content.encode("utf-8")
        mock_response.raise_for_status = MagicMock()

        # Change to tmp dir so output goes there
        monkeypatch.chdir(tmp_path)

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            convert("https://example.com/article")

        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1

    @skip_no_trafilatura
    def test_utf8_no_charset_no_mojibake(self, tmp_path):
        """A UTF-8 page served without a charset must not mojibake.

        requests defaults undeclared text/html to ISO-8859-1, so response.text
        would corrupt '’'/'—'. convert() must decode from response.content
        instead. mock_response.text is set to the Latin-1 mis-decode so a
        regression back to .text would fail this test loudly.
        """
        utf8_html = (
            "<!DOCTYPE html><html><head>"
            "<title>Webb finds a galaxy that doesn’t spin</title></head>"
            "<body><article>"
            "<h1>Webb finds a galaxy that doesn’t spin</h1>"
            "<p>Astronomers spotted something that shouldn’t exist—at least not so "
            "early in the universe. A massive galaxy, formed less than 2 billion "
            "years after the Big Bang, appears to have no rotation at all.</p>"
            "<p>That behavior is normally seen only in large, mature galaxies much "
            "closer to Earth, the researchers explained in the new study.</p>"
            "</article></body></html>"
        )
        raw = utf8_html.encode("utf-8")

        mock_response = MagicMock()
        mock_response.content = raw
        mock_response.text = raw.decode("latin-1")  # what buggy .text would yield
        mock_response.raise_for_status = MagicMock()

        output = tmp_path / "result.md"
        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            convert("https://example.com/galaxy", output=str(output))

        content = output.read_text(encoding="utf-8")
        assert "â" not in content  # no Latin-1 mojibake
        assert "doesn’t spin" in content
        assert "shouldn’t exist—at least" in content

    @skip_no_trafilatura
    def test_image_adjacent_text_neither_lost_nor_duplicated(self, tmp_path):
        """Text flowing after an inline <img> survives exactly once.

        Regression test for the trafilatura image-tail bug: 2.0.0 silently
        dropped the text (`<p><img/>text</p>` — the sentence is the img's lxml
        tail); 2.1.0 emits it twice. The version floor plus dedup_image_tails
        must yield exactly one copy alongside the image embed. Padding
        paragraphs are required: trafilatura prunes images from thin content,
        and a pruned image masks the bug.
        """
        filler = "".join(
            f"<p>Filler sentence number {i}, providing enough body text that "
            f"the extractor retains images during extraction.</p>"
            for i in range(8)
        )
        probe = "They decided to rewrite the code from scratch."
        html = (
            "<html><head><title>Tail Test</title></head><body><article>"
            f"{filler}"
            f'<p><img src="http://example.com/photo.jpg"/>{probe}</p>'
            f"{filler}"
            "</article></body></html>"
        )

        mock_response = MagicMock()
        mock_response.content = html.encode("utf-8")
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.raise_for_status = MagicMock()

        output = tmp_path / "result.md"
        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            convert("https://example.com/tail-test", output=str(output), images=True)

        content = output.read_text(encoding="utf-8")
        assert content.count(probe) == 1  # not lost (2.0.0), not doubled (2.1.0)
        assert "![](figures/" in content  # image embed survived alongside

    @pytest.mark.network
    @skip_no_trafilatura
    def test_real_url(self, tmp_path):
        """Fetches a real public URL."""
        output = tmp_path / "result.md"
        convert("https://en.wikipedia.org/wiki/Markdown", output=str(output))
        assert output.exists()
        content = output.read_text()
        assert "Markdown" in content
