# QA Protocol — Post-Conversion Quality Assurance

QA is format-independent: it operates on the markdown output, whatever the source. Fidelity to
the source text comes first; every rule here serves it. Tiers are defined by **exit criteria**
(what must be true when QA finishes), not procedure — use the cheapest method that satisfies
the contract.

## Tiers

Ask the user once, at conversion start (alongside backend choice), which tier they want, with
rough cost notes. Default to T0 for casual conversions; suggest T1 when the document seems to
matter; T2 only on explicit opt-in.

### T0 — Lint (default; near-zero cost)

Run deterministic checks over the output; fix what is mechanical.

Exit criteria:
- No grep-detectable artifacts remain (see error catalog below).
- Residual-risk note (one paragraph) names what was NOT checked: content fidelity, reading
  order, glyph-level drops.

### T1 — Standard (documents that matter; modest cost)

T0, plus:
- **Reasonable sanity-checking against something independent of the converter.** Which
  invariants matter depends on the document — exercise judgment. Examples: figure / footnote /
  section counts vs. source; per-chapter length within tolerance; section order monotonic;
  numbers spot-matched against the source text layer.
- **Light sampled adversarial text review**: read a few high-risk stretches (tables, equations,
  chapter/page boundaries, frontmatter) with a find-defects brief, plus one short
  checklist-free pass — reviewers find only what a checklist names unless told to be surprised.
- Class triage for everything found (below).

Exit criteria:
- No known S1 (meaning-changing) errors.
- S2 classes fixed or enumerated in the residual-risk note.

### T2 — Audit (opt-in only; expensive — set cost expectations when offering)

T1, plus:
- **Independent review with fresh eyes**: reviewer agent(s) that performed neither the
  conversion nor the fixes, briefed to find defects (not to confirm fixes), iterated until a
  pass comes back dry or the user's budget is reached.
- **Visual comparison against the rendered original, sparingly and targeted** — only where
  text-layer checks are blind (glyph drops: primes, overbars, minus signs; table structure;
  reading order). Not broad page-by-page sweeps.
- Widespread judgment-heavy classes: rework the conversion (different backend/flags) or write
  a smarter fix script first; teams of agents applying manual fixes are a **last resort**.

Exit criteria:
- Quantified coverage statement (what fraction checked, by which method).
- Every fix re-verified against the original.
- Final review pass found nothing new.

### Minimum tier by converter risk

Match the floor to how the backend fails, not just to document importance:

- **ML / OCR backends** (`pdf --backend marker`, `--backend surya`, `--use-llm`, `ocr`) produce
  *fluent* errors — a corrupted digit or an OCR'd `Model`→`Wodel` reads as plausible, so reading
  the output alone has poor recall. **Floor: T1**, and the independence cross-check is
  **mandatory** (not optional) — run the canonical baseline diff (see Independence).
- **Deterministic text paths** (`latex` from source, `epub`, `docx` via pandoc, `url`) extract a
  real text layer, so residual errors are structural and mostly visible on inspection. T0/T1 by
  document importance is fine; a cross-check is still cheap insurance.
- **Scanned PDF, no text layer** (pure OCR, no baseline oracle): the cheapest cross-check is
  unavailable, so each finding costs more to reach. **Floor: T2** when fidelity matters — lean on
  invariant counts and targeted visual sampling, and say so in the residual-risk note.

### Escalation (recommended, never automatic)

- Any S1 found at T0/T1: fix it, then recommend the next tier — where there was one, there are
  likely more.
- High defect density in a T1 sample: recommend widening before shipping.
- For long conversions, QA the first chapters while the rest runs; kill early and switch
  approach if quality is bad.

## Triage discipline

- **Measure before fixing.** Never fix the first instance of an error before counting the
  class (grep for the pattern; estimate prevalence).
- Widespread + mechanical → scripted fix (see Workspace & git).
- Widespread + judgment-required → rework signal (different backend/flags) or a smarter
  script — not a manual repair task (T2 last resort excepted).
- Rare → fix inline.
- **Severity**: S1 meaning-changing, S2 fidelity-degrading, S3 cosmetic. S1 blocks completion
  at every tier; S2 fixed or disclosed; S3 may ship open with a count.
- Before spending judgment on an ambiguous class, look for a deterministic oracle in the
  source (e.g., PDF font spans settle sub- vs. superscript).

## Authority & fidelity

- **Every content fix is a transcription from the original** — cite the page/location that
  authorizes it. Never reconstruct plausible text from memory. (This extends "never transcribe
  equations yourself" to all fixes: the fix must come from the source, via script or reading.)
- As printed by default: source typos are preserved and logged in the deviations note.
  Normalization only where `references/styleguide.md` authorizes it.

## Workspace & git

- All QA artifacts — findings, logs, fix scripts, reports — live in `workspace/` inside the
  output directory. Nothing document-specific leaves it.
- **`git init` trigger is activity, not document size**: initialize the workspace repo the
  first time a script will bulk-edit converted output. Commit the pristine conversion first,
  then one commit per fix application — the script and its effects together — so every bulk
  edit is diffable and revertable.
- Scripted fixes: dry-run the diff on a sample first. Get user sign-off before bulk
  application when a fix touches meaning (S1) or rewrites at scale.
- **Never edit `~/Projects/to-md` during a conversion job.** When a converter bug is confirmed by
  a *concretely failing* minimal repro (input + exact command + expected vs actual), file it as a
  GitHub issue so findings aggregate across runs instead of dying in one workspace:
  - **Dedup first**: `gh issue list --repo adamkhoja1/to-md --search "<symptom>"`. If it already
    exists, add your repro as a comment rather than opening a duplicate.
  - **Self-contained**: a fresh agent with only the issue must be able to reproduce it — paste the
    minimal input (e.g. a ≤10-line `.tex`), the exact command, expected vs actual output, severity
    (S1/S2/S3), and a high-level fix suggestion (not a patch).
  - Keep the runnable repro in `workspace/` and link it. Still never edit the converter yourself.
  - **Speculative** bugs (no failing repro) stay as workspace notes, not issues.

  Likewise for additions to this protocol's error catalog: draft the addition and propose it.

## Independence

- Any ML/OCR-backed conversion (marker, surya, `--use-llm`, `ocr`) gets **at least one
  converter-independent cross-check** — these backends produce fluent errors that evade reading.
- For PDFs with a text layer, the canonical check is **`references/baseline_diff.py`**: it builds
  a pymupdf text-layer baseline and diffs it against the converted output over **both numeric and
  alphabetic tokens** (a numeric-only diff misses OCR word corruption like `Model`→`Wodel`). Run
  it and **save the report in `workspace/`** so the check is reproducible, not ad hoc:
  `uv run --project ~/Projects/to-md python <skill>/references/baseline_diff.py SOURCE.pdf out/`
  On a scanned PDF it reports "no text layer" — that absence is itself the signal to escalate.
- Other paths use the analogous independent source: epub/url already extract deterministically;
  otherwise invariant counts or a targeted comparison against the source text.
- The script self-checks its own tokenizer (`--self-check`) — run that if you doubt a finding.
  More generally, sanity-check any checker on a known-good sample before trusting it; tooling bugs
  produce convincing false findings.

## Token economy

- Detection by script, judgment by model. Deterministic checks are cheap: always run them.
- Findings go to compact workspace files, not context. Sample; don't read everything.

## Error catalog (starting points, not exhaustive)

- **Grep-able**: unexpanded `\commands`; encoding artifacts (mojibake, ligatures, zero-width
  chars); broken `![](figures/...)` paths; heading-level skips or duplicated title lines;
  hyphenation splits; repeated running headers/footers; page-number-only lines; empty
  sections; unbalanced `$` / `$$`; footnote marker/definition mismatches; leftover HTML tags.
- **Needs an independent source**: silent digit/OCR corruption; dropped or duplicated content
  runs; equation-number substitution.
- **Judgment-only**: bullet nesting; table cell alignment; reading order; caption–figure
  association.

When QA surfaces a class not listed here, propose adding it (through the user) so future
conversions start warned.

## Templates

**Residual-risk note** (every tier, scaled to it):

> QA tier: T1. Checked: lint suite clean; figure/footnote counts match source; adversarial
> read of ch. 3, 7, 12. Not checked: glyph-level fidelity outside samples; table semantics in
> ch. 9. Open: 4 S3 list-numbering switches (logged in workspace/qa_log.md).

**Deviations note**:

> p. 214: publisher typo "recieve" preserved as printed. p. 380: bare "b2" normalized to
> $b_2$ per styleguide (consistent with surrounding usage).

**Class log line** (in `workspace/qa_log.md`):

> C3 | running-header leakage | S3 | 13 found | fixed (scripted, commit abc123)
