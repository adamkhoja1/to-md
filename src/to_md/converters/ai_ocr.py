"""AI-assisted OCR for math equations using Claude Vision.

Converts images of math equations to LaTeX. Prompts user with cost
estimate before running.
"""

import base64
import sys
from pathlib import Path

from anthropic import Anthropic
from pydantic import BaseModel


class OCRConfig(BaseModel):
    """Configuration for AI OCR."""

    model: str = "claude-sonnet-4-6-20250217"
    max_tokens: int = 4096


class CostEstimate(BaseModel):
    """Estimated cost for an OCR batch."""

    num_images: int
    estimated_input_tokens: int
    estimated_cost_usd: float


# Average tokens per image (empirical estimate for equation images)
AVG_TOKENS_PER_IMAGE = 1500
# Cost per million input tokens for Claude Sonnet
COST_PER_M_INPUT = 3.0
COST_PER_M_OUTPUT = 15.0
AVG_OUTPUT_TOKENS_PER_IMAGE = 300

SYSTEM_PROMPT = """You are a LaTeX transcription assistant. Given an image of a mathematical equation or expression, output ONLY the LaTeX code that reproduces it. Rules:
- Output raw LaTeX only, no markdown fences or explanation
- Use standard LaTeX math commands
- For display equations, wrap in \\[ ... \\] or $$ ... $$
- For inline math, use $ ... $
- Preserve the exact mathematical content"""


def estimate_cost(image_paths: list[Path]) -> CostEstimate:
    """Estimate the cost of OCR for a batch of images."""
    n = len(image_paths)
    input_tokens = n * AVG_TOKENS_PER_IMAGE
    output_tokens = n * AVG_OUTPUT_TOKENS_PER_IMAGE
    cost = (
        input_tokens * COST_PER_M_INPUT + output_tokens * COST_PER_M_OUTPUT
    ) / 1_000_000
    return CostEstimate(
        num_images=n,
        estimated_input_tokens=input_tokens,
        estimated_cost_usd=cost,
    )


def confirm_with_user(estimate: CostEstimate) -> bool:
    """Display cost estimate and ask for confirmation."""
    print(f"\nAI OCR Cost Estimate:")
    print(f"  Images: {estimate.num_images}")
    print(f"  Estimated tokens: ~{estimate.estimated_input_tokens:,}")
    print(f"  Estimated cost: ~${estimate.estimated_cost_usd:.4f}")
    print()

    response = input("Proceed? [y/N] ").strip().lower()
    return response in ("y", "yes")


def ocr_image(client: Anthropic, image_path: Path, config: OCRConfig) -> str:
    """OCR a single image to LaTeX."""
    image_data = base64.standard_b64encode(image_path.read_bytes()).decode()

    suffix = image_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_types.get(suffix, "image/png")

    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Transcribe this equation to LaTeX.",
                    },
                ],
            }
        ],
    )

    return response.content[0].text


def convert(
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
    paths = [Path(p).resolve() for p in image_paths]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {p}")

    config = OCRConfig(model=model)
    estimate = estimate_cost(paths)

    if not yes:
        if not confirm_with_user(estimate):
            print("Cancelled.")
            sys.exit(0)

    client = Anthropic()
    results: list[str] = []

    for i, path in enumerate(paths, 1):
        print(f"Processing {i}/{len(paths)}: {path.name}...", end=" ", flush=True)
        latex = ocr_image(client, path, config)
        results.append(f"% {path.name}\n{latex}")
        print("done")

    output_text = "\n\n".join(results)

    if output:
        Path(output).write_text(output_text, encoding="utf-8")
        print(f"\nSaved to: {output}")
    else:
        print("\n" + output_text)
