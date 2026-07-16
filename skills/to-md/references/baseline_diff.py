#!/usr/bin/env python
"""Canonical QA cross-check: diff a converted markdown output against a pymupdf
text-layer baseline of the source PDF.

WHY THIS EXISTS
    ML/OCR PDF backends (marker, surya, --use-llm) produce *fluent* errors: a
    corrupted digit or an OCR'd `Model`->`Wodel` reads as perfectly plausible, so
    reading the converted output alone has poor recall. The pymupdf text layer is
    an independent, digit/word-exact source for born-digital PDFs; diffing against
    it surfaces exactly the errors a single backend hides. This is the canonical,
    reproducible form of the qa.md "independence cross-check" — run it and save its
    report in workspace/ instead of hand-rolling an ad-hoc (usually numeric-only)
    diff.

SCOPE & LIMITS
    Prose words + numbers are the reliable signal. Math spans and table cells are
    flattened differently by pymupdf vs the converter, so they are noisy; this tool
    strips obvious markdown/math and reports remaining token-multiset differences.
    It SURFACES suspects for an agent to judge — it is not a pass/fail oracle. A
    scanned PDF has no text layer, so it reports that and exits: the absence of a
    baseline is itself the signal to escalate (invariants + visual sampling).

USAGE
    uv run --project ~/Projects/to-md python baseline_diff.py SOURCE.pdf CONVERTED
        CONVERTED is a .md file or a directory of .md files (top-level, concatenated;
        a workspace/ subdir is skipped).
    --page-range A-B   limit the baseline to pages A..B (0-indexed, inclusive)
    --top N            show at most N items per bucket (default 40)
    --self-check       run the built-in tokenizer/diff self-test and exit
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# Small stopword set — only to cut noise from the "dropped word" bucket, where
# tiny count drifts in function words would otherwise bury real dropped content.
_STOP = frozenset(
    "the a an of to in and or is are was were be been being for on at by with as "
    "that this these those it its from into than then so we our they their he she "
    "his her not no but if all can may will would could should each which who whom".split()
)


def normalize_decimals(text: str) -> str:
    """Rejoin decimals that pymupdf splits, e.g. '41 . 0' / '2 . 3' -> '41.0'."""
    return re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", text)


def strip_markdown(md: str) -> str:
    """Reduce converted markdown to comparable prose + numbers."""
    md = re.sub(r"```.*?```", " ", md, flags=re.DOTALL)      # fenced code
    md = re.sub(r"`[^`]*`", " ", md)                          # inline code
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)             # image embeds
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)          # links -> text
    md = re.sub(r"\$\$.*?\$\$", " ", md, flags=re.DOTALL)     # display math
    md = re.sub(r"\$[^$]*\$", " ", md)                        # inline math
    md = re.sub(r"<[^>]+>", " ", md)                          # html tags
    md = md.replace("|", " ").replace("#", " ").replace("*", " ").replace("_", " ")
    return md


def tokenize(text: str) -> tuple[Counter, Counter]:
    """Return (word multiset, number multiset). Words are length>=2 to drop
    single-letter math variables; numbers keep decimals after normalization."""
    text = normalize_decimals(text).lower()
    words = Counter(re.findall(r"[a-z]{2,}(?:['-][a-z]+)*", text))
    numbers = Counter(re.findall(r"\d+(?:\.\d+)+|\d{2,}", text))
    return words, numbers


def _read_converted(path: Path) -> str:
    if path.is_dir():
        parts = [
            p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted(path.glob("*.md"))
        ]
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="ignore")


def _baseline_text(pdf: Path, page_range: str | None) -> str:
    import fitz  # pymupdf (a to_md core dep)

    doc = fitz.open(pdf)
    lo, hi = 0, doc.page_count - 1
    if page_range:
        a, b = page_range.split("-")
        lo, hi = int(a), int(b)
    return "\n".join(doc[p].get_text() for p in range(lo, min(hi, doc.page_count - 1) + 1))


def diff(baseline: str, converted: str, top: int) -> tuple[str, bool]:
    """Return (report, any_suspects)."""
    b_words, b_nums = tokenize(baseline)
    o_words, o_nums = tokenize(strip_markdown(converted))

    dropped_words = b_words - o_words            # in baseline, missing/changed in output
    added_words = o_words - b_words              # in output only -> OCR-error candidates
    dropped_nums = b_nums - o_nums
    added_nums = o_nums - b_nums

    dropped_content = Counter(
        {w: c for w, c in dropped_words.items() if w not in _STOP}
    )

    def fmt(counter: Counter, label: str) -> str:
        items = counter.most_common(top)
        head = f"{label} ({sum(counter.values())} total, {len(counter)} distinct)"
        if not items:
            return f"  {head}: none"
        body = ", ".join(f"{w}×{c}" if c > 1 else w for w, c in items)
        return f"  {head}:\n    {body}"

    any_suspects = bool(added_words or dropped_content or added_nums or dropped_nums)
    report = "\n".join(
        [
            "=== baseline_diff report (pymupdf text layer vs converted output) ===",
            "Numbers (high-confidence — decimals normalized):",
            fmt(added_nums, "  output-only numbers  [OCR/insertion suspects]"),
            fmt(dropped_nums, "  baseline-only numbers [dropped/changed suspects]"),
            "Words (prose only; math/tables stripped — treat as leads, not verdicts):",
            fmt(added_words, "  output-only words     [OCR-corruption suspects, e.g. Model->Wodel]"),
            fmt(dropped_content, "  baseline-only words   [dropped-content suspects]"),
            "",
            "Note: reordering does not register (multiset diff). Investigate suspects",
            "against the source; math/table tokens may appear here as unavoidable noise.",
        ]
    )
    return report, any_suspects


def self_check() -> int:
    baseline = (
        "The Model achieves a BLEU score of 41.0 on the test set. "
        "Attention is all you need for sequence transduction."
    )
    converted = (
        "The Wodel achieves a BLEU score of 41.8 on the test set."
    )  # Model->Wodel, 41.0->41.8, dropped the second sentence
    b_words, b_nums = tokenize(baseline)
    o_words, o_nums = tokenize(strip_markdown(converted))
    added_words = o_words - b_words
    dropped_words = b_words - o_words
    added_nums = o_nums - b_nums
    dropped_nums = b_nums - o_nums
    checks = {
        "OCR substitution surfaced (wodel)": "wodel" in added_words,
        "changed number surfaced (41.8)": "41.8" in added_nums,
        "original number surfaced (41.0)": "41.0" in dropped_nums,
        "dropped content surfaced (sequence/transduction)": "sequence" in dropped_words
        and "transduction" in dropped_words,
        "correct word surfaced as dropped (model)": "model" in dropped_words,
    }
    ok = all(checks.values())
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print("SELF-CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", nargs="?", help="source PDF")
    ap.add_argument("converted", nargs="?", help="converted .md file or directory")
    ap.add_argument("--page-range", help="A-B, 0-indexed inclusive")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        return self_check()
    if not args.pdf or not args.converted:
        ap.error("pdf and converted are required (or use --self-check)")

    baseline = _baseline_text(Path(args.pdf), args.page_range)
    if len(baseline.strip()) < 200:
        print(
            "NO TEXT LAYER: the PDF yielded almost no extractable text (scanned).\n"
            "The pymupdf baseline cross-check is unavailable — escalate: rely on\n"
            "invariant counts + targeted visual sampling, and disclose in the\n"
            "residual-risk note that no independent text oracle existed."
        )
        return 0

    report, _ = diff(baseline, _read_converted(Path(args.converted)), args.top)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
