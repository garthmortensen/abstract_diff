"""Stage 5b — render executive briefs.

Three Jinja2 templates over the same Stage 4b `ExecutiveSummary`, each a
different reading format for a busy reader: a one-page brief, a
getAbstract-style abstract, and a decision memo (ADR-018). Template logic is
limited to loops and conditionals (R5.1); the pyramid shape comes from the
data, not the template.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from paper_diff.stage4b_write_executive_summary_llm import ExecutiveSummary

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_BRIEFS = {
    "brief_one_page.html": "brief_one_page.html.j2",
    "brief_abstract.html": "brief_abstract.html.j2",
    "brief_decision_memo.html": "brief_decision_memo.html.j2",
}


def render_briefs(summary: ExecutiveSummary) -> dict[str, str]:
    """Render every executive-brief format.

    In: the validated `ExecutiveSummary` from Stage 4b.
    Out: `{output filename: complete HTML document}`, one entry per brief
    template. Every document opens with an AI-generated-content warning and
    badges any evidence quote with `grounded: false`.
    Belongs to: Stage 5b (render executive briefs).
    """
    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)
    return {
        filename: env.get_template(template_name).render(summary=summary)
        for filename, template_name in _BRIEFS.items()
    }
