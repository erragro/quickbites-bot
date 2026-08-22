"""Unit tests for the Mayura chunker.

Tests the pure-Python encode/pack/decode layer without hitting the
Mayura API. Real end-to-end translation is exercised by the ad-hoc
scripts + the Contract Reader flow.
"""

from __future__ import annotations

import pytest

from app.contracts.translate import (
    _canonicalise,
    _decode_chunk,
    _encode_chunk,
    _encoded_length,
    _pack_chunks,
)


def _row(cid: str, exp: str = "e", imp: str = "i", act: str | None = "a") -> dict:
    return {"clause_id": cid, "explanation": exp, "implication": imp, "action": act}


# ---------------------------------------------------------------------------
# Encode / decode roundtrip
# ---------------------------------------------------------------------------


def test_encode_decode_roundtrip_preserves_order_and_fields():
    payloads = [_canonicalise(_row(f"c{i}", f"exp{i}", f"imp{i}", f"act{i}")) for i in range(3)]
    encoded, order = _encode_chunk(payloads)

    # Decode as if Mayura returned the same string unchanged.
    parsed = _decode_chunk(encoded, order)
    assert parsed is not None
    assert set(parsed) == {"c0", "c1", "c2"}
    for i in range(3):
        exp_t, imp_t, act_t = parsed[f"c{i}"]
        assert exp_t.strip() == f"exp{i}"
        assert imp_t.strip() == f"imp{i}"
        assert act_t.strip() == f"act{i}"


def test_encode_uses_row_and_field_markers():
    payloads = [_canonicalise(_row("only", "hello", "world", "act"))]
    encoded, _ = _encode_chunk(payloads)
    assert "[[ROW_1]]" in encoded
    assert "[[FLD]]" in encoded


def test_decode_returns_none_on_missing_markers():
    payloads = [_canonicalise(_row("c0")), _canonicalise(_row("c1"))]
    _, order = _encode_chunk(payloads)

    # Response completely stripped of markers — irrecoverable.
    parsed = _decode_chunk("random text with no markers at all", order)
    assert parsed is None


def test_decode_recovers_partial_when_most_rows_present():
    payloads = [_canonicalise(_row(f"c{i}")) for i in range(4)]
    encoded, order = _encode_chunk(payloads)

    # Simulate Mayura losing one row's markers. Drop the [[ROW_3]] section
    # by stripping any occurrence of it and the following [[FLD]] block.
    corrupted = encoded.split("[[ROW_3]]")[0].rstrip() + "\n"
    parsed = _decode_chunk(corrupted, order)
    # Should still return SOMETHING for the rows we have.
    assert parsed is not None
    assert len(parsed) >= 2


def test_decode_null_when_less_than_half_survives():
    payloads = [_canonicalise(_row(f"c{i}")) for i in range(6)]
    _, order = _encode_chunk(payloads)
    # Almost nothing left — a rare Mayura meltdown.
    parsed = _decode_chunk("[[ROW_1]]\nexp[[FLD]]imp[[FLD]]act\n", order)
    # 1 of 6 rows recovered → below 50% threshold, treated as failure.
    assert parsed is None


# ---------------------------------------------------------------------------
# Chunk packing
# ---------------------------------------------------------------------------


def test_pack_small_rows_into_single_chunk():
    payloads = [_canonicalise(_row(f"c{i}")) for i in range(5)]
    chunks = list(_pack_chunks(payloads, max_chars=800))
    # All 5 tiny rows fit in one chunk.
    assert len(chunks) == 1
    assert len(chunks[0]) == 5


def test_pack_splits_when_row_pushes_over_cap():
    # Force a small cap to test splitting logic.
    big_text = "x" * 200
    payloads = [
        _canonicalise(_row(f"c{i}", exp=big_text, imp=big_text, act=big_text))
        for i in range(4)
    ]
    chunks = list(_pack_chunks(payloads, max_chars=700))
    # 4 rows × ~600 chars each with 700 cap → multiple chunks.
    assert len(chunks) > 1
    for chunk in chunks:
        assert _encoded_length(chunk) <= 700


def test_pack_yields_oversize_row_alone():
    """A single row larger than the cap is yielded on its own so the
    caller can trigger per-field fallback."""
    huge = "x" * 2000
    payloads = [_canonicalise(_row("small")), _canonicalise(_row("huge", exp=huge))]
    chunks = list(_pack_chunks(payloads, max_chars=800))
    # 'small' fits in first chunk; 'huge' becomes its own single-row chunk.
    assert len(chunks) == 2
    assert len(chunks[1]) == 1
    assert chunks[1][0].clause_id == "huge"


def test_pack_empty_input():
    chunks = list(_pack_chunks([], max_chars=800))
    assert chunks == []


# ---------------------------------------------------------------------------
# Canonicalisation preserves None-action semantics
# ---------------------------------------------------------------------------


def test_canonicalise_marks_null_action():
    payload = _canonicalise(_row("c", act=None))
    assert payload.action == ""
    assert payload.action_was_none is True


def test_canonicalise_keeps_string_action():
    payload = _canonicalise(_row("c", act="take this step"))
    assert payload.action == "take this step"
    assert payload.action_was_none is False
