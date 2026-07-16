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
- **Never edit `~/Projects/to-md` during a conversion job.** Suspected converter bug → record
  a minimal repro in the QA log and surface it to the user; the user decides. Likewise for
  additions to this protocol's error catalog: draft the addition and propose it.

## Independence

- Any ML/OCR-backed conversion (marker, `--use-llm`, surya) gets **at least one
  converter-independent cross-check** — these backends produce fluent errors that evade
  reading. Pick the mechanism that fits: text-layer baseline diff (see the PDF QA Workspace
  section of SKILL.md), invariant counts, targeted comparison against source text.
- Sanity-check any checker on a known-good sample before trusting its findings — tooling bugs
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
