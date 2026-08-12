"""
Handlebars-style variable substitution.

Supports:
  {{customer.first_name}}    Nested dotted paths (dict + attribute access
                             both work; misses silently drop the sentence
                             the placeholder was part of, NOT the whole
                             template — see `render`).
  {{order.id}}               Numbers and simple types get str()'d.
  {{customer.name}}          Trailing whitespace around placeholders is
                             preserved so text flows naturally around
                             missing values.

Deliberately NOT supporting:
  {{#if ...}} ... {{/if}}    Block helpers. Templates are single lines
                             / short sentences; complex branching should
                             be handled by having multiple templates
                             pooled per issue type, not by branching
                             inside a template.
  {{helper foo}}             Helper functions. Same reason.

Missing-variable strategy: any placeholder that fails to resolve returns
an empty string AND marks that sentence for elision. The rendered output
never contains a literal `{{...}}`; if resolution fails, the containing
sentence is dropped so we don't leak template scaffolding.
"""

from __future__ import annotations

import re
from typing import Any


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")

# Split a paragraph into sentences on '. ', '! ', '? ' — with the delimiter
# preserved so we can put the paragraph back together minus dropped ones.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _resolve(path: str, context: dict[str, Any]) -> Any:
    """Walk a dotted path through nested dicts / objects. Returns None on
    any miss so callers can decide how to degrade."""
    parts = path.split(".")
    current: Any = context
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _render_sentence(sentence: str, context: dict[str, Any]) -> str | None:
    """Render placeholders in a single sentence. Returns None if any
    placeholder failed to resolve — signalling the sentence should be
    dropped from the final output."""
    missed = False

    def sub(m: re.Match[str]) -> str:
        nonlocal missed
        path = m.group(1)
        value = _resolve(path, context)
        if value is None or (isinstance(value, str) and not value.strip()):
            missed = True
            return ""
        return str(value)

    rendered = _PLACEHOLDER_RE.sub(sub, sentence)
    if missed:
        return None
    return rendered


def render(template: str, context: dict[str, Any]) -> str:
    """
    Render `template` with variables from `context`. Missing variables
    cause the enclosing sentence to be dropped, NOT to appear as
    `{{path}}` in the output.

    If ALL sentences fail to render (edge case: template is one
    sentence and its only variable is missing), returns a neutral
    non-empty fallback so the caller doesn't have to null-check.
    """
    if not template:
        return ""

    sentences = _SENTENCE_RE.split(template.strip())
    kept: list[str] = []
    for s in sentences:
        rendered = _render_sentence(s, context)
        if rendered is not None:
            kept.append(rendered.strip())

    if not kept:
        # Every sentence had a missing variable. Fall back to something
        # neutral rather than an empty string. Rare in practice —
        # requires ALL placeholders to fail, meaning the enricher pulled
        # nothing at all.
        return "I'm on it — let me pull up the details."

    return " ".join(kept)
