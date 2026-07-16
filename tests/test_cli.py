"""Tests for to_md.cli — CLI dispatch.

Tests verify that CLI methods correctly dispatch to converter functions.
"""

import subprocess
import sys
from unittest.mock import patch

import pytest

from to_md.cli import CLI


class TestCLIDispatch:
    def test_latex_dispatch(self):
        cli = CLI()
        with patch("to_md.converters.latex.convert") as mock:
            cli.latex("input.tex", "output/")
            mock.assert_called_once_with(
                "input.tex",
                "output/",
                no_split=False,
                no_figures=False,
                image_dir="figures",
                no_bib=False,
                flatten_only=False,
            )

    def test_pdf_dispatch(self):
        cli = CLI()
        with patch("to_md.converters.pdf.convert") as mock:
            cli.pdf("input.pdf", "output/")
            mock.assert_called_once_with(
                "input.pdf",
                "output/",
                split_chapters=False,
                no_images=False,
                image_dir="figures",
                backend="pymupdf",
                use_llm=False,
                page_range="",
            )

    def test_epub_dispatch(self):
        cli = CLI()
        with patch("to_md.converters.epub.convert") as mock:
            cli.epub("input.epub", "output/")
            mock.assert_called_once_with(
                "input.epub",
                "output/",
                no_images=False,
                image_dir="figures",
            )

    def test_docx_dispatch(self):
        cli = CLI()
        with patch("to_md.converters.docx.convert") as mock:
            cli.docx("input.docx")
            mock.assert_called_once_with(
                "input.docx", output_dir=None, no_images=False, image_dir="figures"
            )

    def test_url_dispatch(self):
        cli = CLI()
        with patch("to_md.converters.url.convert") as mock:
            cli.url("https://example.com")
            mock.assert_called_once_with(
                "https://example.com",
                output=None,
                images=False,
                split=False,
                image_dir="figures",
            )

    def test_pdf_with_options(self):
        cli = CLI()
        with patch("to_md.converters.pdf.convert") as mock:
            cli.pdf("input.pdf", "output/", split_chapters=True, backend="pymupdf", page_range="0-5")
            mock.assert_called_once_with(
                "input.pdf",
                "output/",
                split_chapters=True,
                no_images=False,
                image_dir="figures",
                backend="pymupdf",
                use_llm=False,
                page_range="0-5",
            )

    def test_cli_help(self):
        """python -m to_md -- --help should exit cleanly."""
        result = subprocess.run(
            [sys.executable, "-m", "to_md", "--", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # fire prints help and exits with 0
        assert result.returncode == 0
        # fire outputs help to stderr
        output = result.stdout + result.stderr
        assert "SYNOPSIS" in output or "NAME" in output or "latex" in output.lower()
