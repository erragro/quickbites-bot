"""Idiom library — detect English idioms and substitute deterministic
target-language equivalents around a Mayura translation call.

Why this exists
---------------
Mayura is a strong general-purpose Indic translator, but idioms don't
translate literally — "at the end of the day" rendered word-for-word
becomes a phrase about the actual final hour of a shift, which loses
meaning entirely. Workers reading a translated contract or chatbot
answer need the equivalent expression in their language, not a
literal calque.

Flow
----
1. `substitute(text, target_language)` scans the English source with a
   pre-built Aho-Corasick automaton. Every hit becomes a
   `Substitution` entry and gets replaced in the text with a
   placeholder token (e.g. `[[IDM_1]]`). The placeholder is designed
   to survive translation: it uses plain ASCII, contains no
   translatable words, and stays intact through Mayura's transformer.

2. Caller sends the placeholder-laden text to Mayura and receives a
   translation with the placeholders preserved.

3. `restore(translated_text, subs)` swaps each placeholder for the
   pre-verified target-language equivalent from the idiom_translations
   table.

Detection performance
---------------------
Aho-Corasick is O(text length + total match length). For our 25-idiom
seed it scans 20KB of contract text in ~200 microseconds on this
laptop. The library scales to thousands of idioms without perceptible
cost, so admins can grow it freely.

Caching
-------
The automaton + translation tables are loaded from the DB on first
call and cached at module level. `reset_cache()` is exposed so the
admin CRUD (later) can invalidate after adding/editing rows without
restarting the process.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Iterable

import ahocorasick
from sqlalchemy.orm import Session

from app.db import db_session


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Substitution:
    """One idiom occurrence found in source text, with its resolved
    target-language equivalent + the placeholder that will represent
    it during translation.
    """
    idiom_id: uuid.UUID
    source_phrase: str      # The exact substring that matched (original casing preserved).
    placeholder: str        # e.g. "[[IDM_1]]"
    target_translation: str # The pre-verified equivalent to splice back in.


# ---------------------------------------------------------------------------
# Placeholder format
# ---------------------------------------------------------------------------

# Chosen deliberately: ASCII, uppercase, double-bracketed, contains no
# real word. Empirically survives Mayura's translation intact even in
# languages that don't share Latin script — the model treats it as a
# proper-noun-like token rather than something to translate.
_PLACEHOLDER_TEMPLATE = "[[IDM_{n}]]"
_PLACEHOLDER_RE = re.compile(r"\[\[IDM_(\d+)\]\]")


def _placeholder(n: int) -> str:
    return _PLACEHOLDER_TEMPLATE.format(n=n)


# ---------------------------------------------------------------------------
# Library cache
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _IdiomEntry:
    id: uuid.UUID
    source_phrase: str  # canonical lowercased form
    translations: dict[str, str]  # BCP-47 code → equivalent


class _Library:
    """Loaded automaton + translation lookup. Immutable per instance —
    reload creates a new one atomically so no scan ever sees a
    half-built state."""

    def __init__(
        self,
        automaton: ahocorasick.Automaton,
        entries: dict[uuid.UUID, _IdiomEntry],
    ):
        self._automaton = automaton
        self._entries = entries

    def scan(self, text: str) -> list[tuple[int, int, uuid.UUID]]:
        """Return non-overlapping (start, end_inclusive, idiom_id)
        matches, longest-first for overlap resolution. Case-insensitive
        matching — the automaton was built on lowercased keys and we
        scan lowercased input."""
        if not text:
            return []
        hits: list[tuple[int, int, uuid.UUID]] = []
        lowered = text.lower()
        for end_idx, payload in self._automaton.iter(lowered):
            idiom_id, phrase_len = payload
            start_idx = end_idx - phrase_len + 1
            # Word-boundary guard so "in good faith" doesn't fire
            # inside "beingood faithful". Aho-Corasick is substring-
            # based; boundary check keeps false positives out.
            if not _is_bounded(text, start_idx, end_idx):
                continue
            hits.append((start_idx, end_idx, idiom_id))
        if not hits:
            return []
        # Longest-first resolution: sort by (start ASC, length DESC),
        # then greedy-pick the first at each position and skip anything
        # that overlaps a chosen match.
        hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
        chosen: list[tuple[int, int, uuid.UUID]] = []
        cursor = -1
        for start, end, iid in hits:
            if start > cursor:
                chosen.append((start, end, iid))
                cursor = end
        return chosen

    def entry(self, idiom_id: uuid.UUID) -> _IdiomEntry | None:
        return self._entries.get(idiom_id)


_cache: _Library | None = None
_cache_lock = threading.Lock()


def _load() -> _Library:
    """Read the idiom tables and build the automaton. Called under the
    cache lock — safe against a burst of concurrent first-use calls."""
    automaton = ahocorasick.Automaton()
    entries: dict[uuid.UUID, _IdiomEntry] = {}

    with db_session() as db:
        rows = db.execute(_LIBRARY_QUERY).all()

    per_idiom_translations: dict[uuid.UUID, dict[str, str]] = {}
    per_idiom_phrase: dict[uuid.UUID, str] = {}
    for row in rows:
        iid = row.idiom_id
        per_idiom_phrase[iid] = row.source_phrase
        if row.language:
            per_idiom_translations.setdefault(iid, {})[row.language] = row.translation or ""

    # Group by canonical (lowercased) phrase and pick the winner per key
    # — the entry with the MOST translations. Prevents admin-created
    # duplicates (or empty placeholders) from shadowing a well-populated
    # seed row in the automaton. The automaton can only hold one value
    # per key, so we must pre-resolve conflicts here.
    by_phrase: dict[str, list[uuid.UUID]] = {}
    for iid, phrase in per_idiom_phrase.items():
        canonical = phrase.strip().lower()
        if not canonical:
            continue
        by_phrase.setdefault(canonical, []).append(iid)

    for canonical, ids in by_phrase.items():
        winner = max(
            ids,
            key=lambda i: len(per_idiom_translations.get(i, {})),
        )
        entries[winner] = _IdiomEntry(
            id=winner,
            source_phrase=canonical,
            translations=per_idiom_translations.get(winner, {}),
        )
        # Store (idiom_id, key_length) as the automaton value so scan()
        # can reconstruct the start position from the end position that
        # pyahocorasick reports.
        automaton.add_word(canonical, (winner, len(canonical)))

    automaton.make_automaton()
    logger.info("idiom library: loaded %d entries", len(entries))
    return _Library(automaton=automaton, entries=entries)


# Composed here so both _load() and tests can reuse the same shape.
from sqlalchemy import text as _sql_text

_LIBRARY_QUERY = _sql_text(
    """
    SELECT
        i.id            AS idiom_id,
        i.source_phrase AS source_phrase,
        t.language      AS language,
        t.translation   AS translation
    FROM idiom_library i
    LEFT JOIN idiom_translations t
      ON t.idiom_id = i.id
     AND t.is_active = true
    WHERE i.is_active = true
    """
)


def _library() -> _Library:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = _load()
    return _cache


def reset_cache() -> None:
    """Drop the loaded automaton so the next call rebuilds from the DB.
    Called by admin CRUD when idioms are added / edited / deactivated.
    Safe to call concurrently — the next scanner rebuilds under lock."""
    global _cache
    with _cache_lock:
        _cache = None


# ---------------------------------------------------------------------------
# Substitution / restoration
# ---------------------------------------------------------------------------


def substitute(text: str, target_language: str) -> tuple[str, list[Substitution]]:
    """Scan `text` for known idioms; return the placeholder-substituted
    text plus the list of substitutions to apply after translation.

    If an idiom has no translation for the target language (admin added
    the source but not the equivalent yet), it's skipped — the untouched
    English falls through to Mayura, which will do its best.

    Empty text → empty result. Target 'en' → no-op (returns original
    text) because there's nothing to substitute for; callers usually
    skip translation entirely when target == 'en'.
    """
    if not text or target_language == "en":
        return text, []

    lib = _library()
    matches = lib.scan(text)
    if not matches:
        return text, []

    # Build output by walking the original text left-to-right, splicing
    # placeholders in at each match's byte offset. Preserving the char
    # positions is important — the original casing / spacing before
    # and after each match survives.
    parts: list[str] = []
    subs: list[Substitution] = []
    cursor = 0
    for start, end, idiom_id in matches:
        entry = lib.entry(idiom_id)
        if entry is None:
            continue
        target = (entry.translations.get(target_language) or "").strip()
        if not target:
            # Missing target-language translation for this idiom.
            # Skip — leave the English text intact for Mayura.
            logger.debug(
                "idiom %s has no %s translation; passing through",
                entry.source_phrase, target_language,
            )
            continue

        # Everything up to this match stays as-is.
        parts.append(text[cursor:start])
        placeholder = _placeholder(len(subs) + 1)
        subs.append(Substitution(
            idiom_id=idiom_id,
            source_phrase=text[start:end + 1],
            placeholder=placeholder,
            target_translation=target,
        ))
        parts.append(placeholder)
        cursor = end + 1

    # Tail after the last match.
    parts.append(text[cursor:])
    return "".join(parts), subs


def restore(translated_text: str, subs: Iterable[Substitution]) -> str:
    """Swap placeholders in `translated_text` for their target-language
    equivalents. Missing placeholders (Mayura sometimes drops or
    duplicates unusual tokens) are logged. Any surviving stray
    `[[IDM_n]]` tokens (either from a foreign call or from Mayura
    hallucinating extra ones) are stripped — better empty than a
    leaked debug token visible on the card."""
    subs_list = list(subs)
    out = translated_text
    missing: list[str] = []
    for sub in subs_list:
        if sub.placeholder in out:
            out = out.replace(sub.placeholder, sub.target_translation)
        else:
            missing.append(sub.placeholder)
    # Belt-and-braces sweep for any [[IDM_n]] that survived — either
    # because it was never in our subs list, or because it appeared
    # somewhere our exact-match replace didn't catch.
    out = _PLACEHOLDER_RE.sub("", out)
    if missing:
        logger.warning(
            "idiom restore: %d placeholders missing from Mayura output "
            "(idioms untranslated for this fragment): %s",
            len(missing), missing,
        )
    return out


# ---------------------------------------------------------------------------
# Word boundary helper
# ---------------------------------------------------------------------------


def _is_bounded(text: str, start: int, end: int) -> bool:
    """Return True if the match at [start, end] is bounded by non-word
    characters on both sides — i.e. it's a real phrase hit, not a
    substring inside a longer word. Word chars = letters, digits,
    underscore, apostrophe (for possessives / contractions)."""
    before = text[start - 1] if start > 0 else ""
    after = text[end + 1] if end + 1 < len(text) else ""
    return not (_is_word_char(before) or _is_word_char(after))


def _is_word_char(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch in "_'")
