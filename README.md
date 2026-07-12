# to-md

Convert documents to Markdown.

Supported inputs: LaTeX (`.tex`, arXiv), PDF, EPUB, DOCX, and web URLs. Math is
preserved as LaTeX.

## Usage

Run via the module, one subcommand per input type:

```bash
uv run python -m to_md latex <arxiv-id|.tex|.zip> <output_dir>
uv run python -m to_md pdf   <input.pdf> <output.md>
uv run python -m to_md epub  <input.epub> <output_dir>
uv run python -m to_md docx  <input.docx> [output_dir]
uv run python -m to_md url   <url> [output.md]
uv run python -m to_md ocr   <equation.png ...> --output out.tex
```

Append `--help` to any subcommand for its full set of options.
