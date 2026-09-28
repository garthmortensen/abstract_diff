"""Stage 5 — render report.

One Jinja2 template (`templates/report.html.j2`). Template logic is limited
to loops and conditionals (R5.1); all shaping of the data happened at
Stage 4.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from paper_diff.stage4_assemble_and_validate_comparison import Comparison

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_report(comparison: Comparison) -> str:
    """Render the final HTML report.

    In: the validated `Comparison` from Stage 4.
    Out: a complete HTML document as a string, with a visible badge on any
    `grounded: false` assertion (R5.2) and any `index_corrected: true`
    assertion (R5.3).
    Belongs to: Stage 5 (render report).
    """
    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)
    template = env.get_template("report.html.j2")
    return template.render(comparison=comparison)
