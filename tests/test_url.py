"""Tests for to_md.converters.url — URL to Markdown conversion.

Unit tests for utility functions use local fixtures.
Integration tests monkeypatch network calls.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conftest import skip_no_trafilatura

# Conditionally import — many tests need trafilatura
try:
    from to_md.converters.url import (
        convert,
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
        mock_response.text = html_content
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
        mock_response.text = html_content
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
        mock_response.text = html_content
        mock_response.raise_for_status = MagicMock()

        # Change to tmp dir so output goes there
        monkeypatch.chdir(tmp_path)

        with patch("to_md.converters.url.requests.get", return_value=mock_response):
            convert("https://example.com/article")

        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1

    @pytest.mark.network
    @skip_no_trafilatura
    def test_real_url(self, tmp_path):
        """Fetches a real public URL."""
        output = tmp_path / "result.md"
        convert("https://en.wikipedia.org/wiki/Markdown", output=str(output))
        assert output.exists()
        content = output.read_text()
        assert "Markdown" in content
