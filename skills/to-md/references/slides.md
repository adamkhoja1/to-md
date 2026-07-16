# Slides (.txt) → Markdown — Detailed Heuristics

Reference for converting Google Slides "Download as Plain Text" exports into structured Markdown.
This is an **LLM interpretation task — there is no script.** The text export strips all formatting,
so structure must be inferred from context.

## Google Slides Text Export Format

These properties are consistent across Google Slides "Download as Plain Text" exports:

1. **All formatting stripped** — no bold, italic, font size, color, or indentation survives
2. **Blank lines are the only structural delimiter** — 1+ blank lines between slides/text boxes
3. **First line = presentation title**, alone, followed by a blank line
4. **After blank lines, first non-blank line = slide title** — shorter, Title/Sentence Case, typically no trailing period
5. **Section divider slides** = a title line with no content before the next blank line
6. **Content lines** follow titles, are longer, often end in punctuation
7. **Sub-bullet hierarchy is flattened** — no indentation preserved; must infer from semantics
8. **Tables → sequential plain-text lines** — headers as short lines, data as longer lines, no delimiters
9. **Special markers**: `*` prefix = notes/annotations; `[brackets]` = placeholders; `"quotes"` = direct quotes; `Figure:` = images/diagrams
10. **Multiple consecutive blank lines** = empty visual areas (image placeholders, spacers)
11. **Repeated text** — section dividers often echo the title of the next content slide

## Conversion Process

### Step 1: Full Read Pass

Read the entire file first. Understand the subject matter, presentation arc, and whether the file uses consistent conventions. Do not start converting until the full structure is understood.

### Step 2: Identify Slide Boundaries

Segment into slides using these heuristics (priority order):

1. **Blank-line separation** — 1+ blank lines between text blocks = slide boundary
2. **Title detection** — after a boundary, first non-blank line is the candidate title. Confirm: shorter than following lines? Title Case? No trailing period? Introduces/summarizes what follows?
3. **Section dividers** — title with no content before next blank = section divider slide
4. **Continuation grouping** — if blocks separated by one blank share a topic (e.g., a table split across "chunks"), group into one slide

### Step 3: Classify and Format Elements

| Element | Identification | Markdown |
|---------|---------------|----------|
| Presentation title | First line of file | `# Title` |
| Section divider | Title-only slide introducing a major section | `## Section Title` |
| Slide title | First line after blank(s); heading-style | `### Slide Title` |
| Subtitle/tagline | Short line right after title, before main content | `*Italic line*` |
| Main bullet | Introduces a distinct point | `- **Key phrase**: explanation` |
| Sub-bullet | Elaborates/exemplifies preceding bullet | `  - Sub-point` |
| Table | Parallel-structure sequential lines | Markdown table |
| Figure reference | `Figure:` prefix | `> *[Figure: description]*` |
| Quote | In quotation marks | `> "Quoted text"` |
| Note/annotation | `*` prefix or `[brackets]` | `*[Note: content]*` |
| Roadmap items | Sequential short lines listing topics | Ordered list |

### Step 4: Infer Sub-Bullet Hierarchy

This is the hardest part. Use these signals:

- **Specificity gradient** — line B is more specific than A (example, technique, case) → B is sub-bullet of A
- **"e.g." / "such as" / "Example:"** — strong sub-bullet signal
- **Category → instances** — A names a category, B/C/D name specific instances → sub-bullets
- **Continuation** — removing B leaves A incomplete → B is sub-bullet
- **New topic** — B introduces a different concept → new main bullet
- **Parallel structure** — same grammatical pattern at same conceptual level → siblings, not parent-child

### Step 5: Apply Formatting

- **Bold key terms** in "term: explanation" patterns
- **Reconstruct tables** with proper Markdown syntax; if ambiguous, use bulleted list with bold labels instead
- **Horizontal rules** (`---`) between major sections (corresponding to section dividers)
- **Blockquotes** for direct quotes and figure references

### Step 6: Review

1. Heading hierarchy makes sense (`#` → `##` → `###`)
2. No content dropped from original
3. Sub-bullet nesting reflects semantic relationships
4. Tables properly formatted

## Example

**Input** (text export):
```
Project Overview

Key Goals
Increase user retention by 20%
Focus on mobile experience
Improve onboarding flow
Reduce time-to-value for new users
Launch by Q3 2025

Technical Approach
Microservices architecture
API gateway for routing
Service mesh for internal communication
React Native for cross-platform mobile
Shared component library across iOS and Android
```

**Output** (Markdown):
```markdown
# Project Overview

---

### Key Goals

- **Increase user retention by 20%** — focus on mobile experience
- **Improve onboarding flow**
  - Reduce time-to-value for new users
- **Launch by Q3 2025**

### Technical Approach

- **Microservices architecture**
  - API gateway for routing
  - Service mesh for internal communication
- **React Native** for cross-platform mobile
  - Shared component library across iOS and Android
```

Note how sub-bullets are inferred: "API gateway" and "Service mesh" elaborate on the microservices architecture; "Reduce time-to-value" specifies what "improve onboarding flow" means.

## Output

Save as `[original-filename].md` in the same directory as the source file (or wherever the user requests).

## Edge Cases

- **Ambiguous boundaries** — prefer grouping blocks that share a topic into one slide
- **Repeated text** — use section divider as `##`, adjust duplicate slide title to `###` or omit
- **Very long slides** — preserve all content, never summarize or truncate
- **Speaker notes** — more conversational/meta lines should be marked as `> *[Note: ...]*`

## Customization

Users can request:
- **Heading offset** — start slides at `##` instead of `###`
- **Flat bullets** — skip sub-bullet inference, keep everything at one level
- **Slide numbers** — include `<!-- Slide N -->` comments
- **Include/exclude annotations** — keep or strip `*[Note: ...]*` markers
