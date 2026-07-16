# Output Styleguide — Converted Markdown

**Fidelity to the source text comes first.** No style rule below ever overrides content
fidelity. This guide covers high-level presentation choices only — it deliberately avoids
document-specific conventions, and grows as the skill is exercised on real texts (propose
additions through the user).

## 1. Fidelity stance

- Reproduce the text as printed. Do not correct, modernize, or paraphrase.
- Source errors (publisher typos, inconsistent notation) are preserved as printed and recorded
  in the deviations note (template in `references/qa.md`).
- Normalization happens only where a rule below explicitly authorizes it — never by
  per-conversion taste.

## 2. Markdown house style (Obsidian-flavored)

- **Math**: inline `$...$`, display `$$...$$`. Numbered equations keep their printed number
  via `\tag{N.M}` inside the display block — don't strand the number outside the math.
- **Footnotes**: Obsidian syntax (`[^n]` marker, `[^n]:` definition), definitions at the end
  of the file they occur in — never stranded mid-text.
- **Headings**: number and title on one heading line (`# Chapter N: Title`) — never split
  across two heading lines. Levels descend without skips.
- **No raw HTML where markdown or math suffices** (no `<sup>`/`<sub>` for what `$...$`
  expresses).

## 3. Figures

- Embed with a relative path into the `figures/` directory per the output structure.
- **The caption always appears as searchable text adjacent to the embed** (below it), even if
  the caption is also baked into the image.
- Alt text: one short line stating what the figure shows.
- Complex diagrams that carry meaning the text doesn't restate (graphs, trees, schematics):
  add a brief long-description under the caption.
- Figure-internal text (axis labels, curve labels): decide explicitly per conversion whether
  it needs a text representation; record the decision in the residual-risk note.
