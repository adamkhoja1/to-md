"""Unified CLI for to_md converters."""

import fire


class CLI:
    """Convert documents to Markdown.

    Subcommands: latex, pdf, epub, docx, url, ocr
    """

    def latex(
        self,
        source: str,
        output_dir: str,
        no_split: bool = False,
        no_figures: bool = False,
        image_dir: str = "figures",
        no_bib: bool = False,
        flatten_only: bool = False,
    ) -> None:
        """Convert LaTeX source to Markdown.

        Args:
            source: arXiv ID, arXiv URL, .tex path, .zip, or .tar.gz.
            output_dir: Output directory for markdown files.
            no_split: Single output.md instead of per-section files.
            no_figures: Skip figure conversion/copying.
            image_dir: Figures subdirectory name.
            no_bib: Skip bibliography processing.
            flatten_only: Only produce flattened.tex, stop.
        """
        from to_md.converters.latex import convert

        convert(
            source,
            output_dir,
            no_split=no_split,
            no_figures=no_figures,
            image_dir=image_dir,
            no_bib=no_bib,
            flatten_only=flatten_only,
        )

    def pdf(
        self,
        input_pdf: str,
        output: str,
        split_chapters: bool = False,
        no_images: bool = False,
        image_dir: str = "figures",
        backend: str = "pymupdf",
        use_llm: bool = False,
        page_range: str = "",
    ) -> None:
        """Convert PDF to Markdown.

        Args:
            input_pdf: Path to input PDF file.
            output: Output file (.md) or directory.
            split_chapters: Split into separate files at H1 headings.
            no_images: Skip image extraction.
            image_dir: Name of figures directory.
            backend: Conversion backend (pymupdf, marker, surya).
            use_llm: Enable LLM-assisted conversion (marker backend).
            page_range: Page range as "start-end" (0-indexed, inclusive).
        """
        from to_md.converters.pdf import convert

        convert(
            input_pdf,
            output,
            split_chapters=split_chapters,
            no_images=no_images,
            image_dir=image_dir,
            backend=backend,
            use_llm=use_llm,
            page_range=page_range,
        )

    def epub(
        self,
        input_epub: str,
        output: str,
        no_images: bool = False,
        image_dir: str = "figures",
    ) -> None:
        """Convert EPUB to Markdown.

        Args:
            input_epub: Path to input EPUB file.
            output: Output directory.
            no_images: Skip image extraction.
            image_dir: Name of figures directory.
        """
        from to_md.converters.epub import convert

        convert(
            input_epub,
            output,
            no_images=no_images,
            image_dir=image_dir,
        )

    def docx(
        self,
        source: str,
        output_dir: str | None = None,
        no_images: bool = False,
        image_dir: str = "figures",
    ) -> None:
        """Convert DOCX to Markdown.

        Args:
            source: Path to a .docx file or glob pattern.
            output_dir: Optional output directory.
            no_images: Strip images instead of extracting them.
            image_dir: Name of figures directory.
        """
        from to_md.converters.docx import convert

        convert(
            source,
            output_dir=output_dir,
            no_images=no_images,
            image_dir=image_dir,
        )

    def url(
        self,
        url: str,
        output: str | None = None,
        images: bool = False,
        split: bool = False,
        image_dir: str = "figures",
    ) -> None:
        """Convert URL to Markdown.

        Args:
            url: The URL to fetch and convert.
            output: Output file (.md) or directory.
            images: Download images to figures/ directory.
            split: Split into separate files at H1/H2 headings.
            image_dir: Name of figures directory.
        """
        from to_md.converters.url import convert

        convert(
            url,
            output=output,
            images=images,
            split=split,
            image_dir=image_dir,
        )

    def ocr(
        self,
        *image_paths: str,
        output: str = "",
        model: str = "claude-sonnet-4-6-20250217",
        yes: bool = False,
    ) -> None:
        """OCR math equation images to LaTeX.

        Args:
            image_paths: Paths to equation images.
            output: Output file for LaTeX results (stdout if empty).
            model: Claude model to use.
            yes: Skip confirmation prompt.
        """
        from to_md.converters.ai_ocr import convert

        convert(*image_paths, output=output, model=model, yes=yes)


def main() -> None:
    fire.Fire(CLI)
