"""In-house OCR for uploaded contract files.

Backed by EasyOCR (open-source, runs locally, PyTorch) and PyMuPDF (for
PDF page rendering). Worker contracts stay on our infrastructure — no
per-scan cost, no vendor dependency, and a real "built for India"
story for the pitch. Swaps in for Gemini vision after the 2026-08-15
architecture pivot.

Language routing:
  EasyOCR requires you to construct a Reader per language set, and
  can only mix Latin (English) with one non-Latin script per reader
  (Devanagari OR Bengali OR Tamil — not two together). We keep a
  cache of readers by language tuple.

  Callers pass a source language hint (from the upload form). If the
  worker picked 'auto' or left it blank, we default to ('en', 'hi') —
  covers most Indian gig-worker contracts. If they picked a specific
  Indic language, we spin up (or reuse) the matching reader.

First-call cost:
  Reader init downloads the language model (~100MB per language pair)
  on first use, then caches to ~/.EasyOCR. Subsequent uploads reuse
  the loaded reader instantly. Startup pre-warm is possible but not
  yet wired — the first upload for each language pair takes a hit.
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OCRResult:
    text: str
    language: Optional[str]  # BCP-47 short code, mirrors the source hint
    is_low_quality: bool     # True when extracted text is suspiciously short


# ---------------------------------------------------------------------------
# Language routing
# ---------------------------------------------------------------------------

# EasyOCR uses its own language codes; almost always these match our BCP-47
# short codes but a couple diverge (Marathi shares Devanagari with Hindi
# via the 'mr' code; Assamese is 'as' but not in our target set).
_SUPPORTED_INDIC = {"hi", "bn", "ta", "te", "kn", "mr"}


def _reader_langs_for(source_hint: Optional[str]) -> tuple[str, ...]:
    """Which EasyOCR languages to load for a given source-language hint.

    Every reader includes English so Latin script (numbers, section
    headers, English clauses in bilingual contracts) is always recognised.
    """
    hint = (source_hint or "").lower().strip()
    if hint in _SUPPORTED_INDIC and hint != "en":
        return ("en", hint)
    # 'en', 'auto', or unknown → default combo covers most Indian contracts.
    return ("en", "hi")


# ---------------------------------------------------------------------------
# Reader cache
#
# EasyOCR Reader construction is expensive: it loads PyTorch models into
# memory and, on first call for a language, downloads the pretrained
# weights. Keep one reader per language tuple, protected by a lock so a
# burst of concurrent uploads doesn't race the constructor.
# ---------------------------------------------------------------------------


_READERS: dict[tuple[str, ...], "object"] = {}
_READERS_LOCK = threading.Lock()


def _get_reader(languages: tuple[str, ...]):
    """Return a cached EasyOCR Reader for the given language tuple. Loads
    (and caches) on first call. Not called at import time — deferred so
    the module loads fast even before OCR is needed."""
    with _READERS_LOCK:
        if languages not in _READERS:
            import easyocr  # noqa: WPS433 — deferred to keep module load cheap
            logger.info(
                "OCR: initialising EasyOCR reader for languages=%s "
                "(first call may download ~100MB of language weights)",
                languages,
            )
            _READERS[languages] = easyocr.Reader(
                list(languages),
                gpu=False,
                verbose=False,
            )
        return _READERS[languages]


# ---------------------------------------------------------------------------
# File → images
# ---------------------------------------------------------------------------


def _pdf_to_images(pdf_bytes: bytes, *, dpi: int = 200) -> list[np.ndarray]:
    """Rasterise every page of a PDF to a numpy image array. 200 dpi
    gives EasyOCR enough resolution to read 10pt body text cleanly
    without ballooning memory (a typical A4 page → ~2 MB uint8 array)."""
    import fitz  # noqa: WPS433 — PyMuPDF, imported lazily

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages: list[np.ndarray] = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            # pixmap.samples is a bytes buffer; reshape into (h, w, channels).
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n,
            )
            pages.append(arr)
        return pages
    finally:
        doc.close()


def _image_to_array(image_bytes: bytes) -> np.ndarray:
    """Decode an image blob to numpy. Converts to RGB up front so
    palettised PNGs and single-channel greyscales normalise cleanly."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    return np.array(img)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# When output text is below this length we flag is_low_quality — either
# the source is blank, garbled, or the worker uploaded the wrong file.
_LOW_QUALITY_THRESHOLD = 80


def extract_text(
    file_bytes: bytes,
    mime_type: str,
    *,
    source_language: Optional[str] = None,
) -> OCRResult:
    """Extract the text from a contract file.

    source_language is a BCP-47 code from the upload form ('hi', 'bn',
    'ta', 'te', 'kn', 'mr', 'en'). Missing or 'auto' → default to
    English + Devanagari, which covers the majority of Indian gig-worker
    contracts. Callers get back the extracted text and echo of the
    source language for downstream stages.
    """
    reader = _get_reader(_reader_langs_for(source_language))

    if mime_type == "application/pdf":
        try:
            pages = _pdf_to_images(file_bytes)
        except Exception as exc:
            logger.exception("OCR: failed to rasterise PDF")
            raise RuntimeError(f"could not read PDF: {exc}") from exc
    else:
        # image/png, image/jpeg — the routes layer already whitelisted MIME.
        pages = [_image_to_array(file_bytes)]

    if not pages:
        return OCRResult(text="", language=source_language, is_low_quality=True)

    all_text: list[str] = []
    for page_no, page_img in enumerate(pages, start=1):
        try:
            # detail=0 → return plain text (drops bounding-box coords).
            # paragraph=True → glue nearby boxes into paragraphs, which
            # matches how contract text actually flows and gives Stage 1
            # sensible clause chunks to work with.
            lines = reader.readtext(page_img, detail=0, paragraph=True)
        except Exception as exc:
            logger.exception("OCR: page %d failed", page_no)
            # Skip the failed page rather than fail the whole document —
            # a bad page still leaves the rest usable.
            lines = []
        for line in lines:
            if isinstance(line, str) and line.strip():
                all_text.append(line.strip())
        if len(pages) > 1 and page_no < len(pages):
            # Page separator so Stage 1 sees the same structure the PDF
            # had. Two blank lines is a strong-enough hint for the clause
            # extractor without being a special token.
            all_text.append("")

    text = "\n".join(all_text).strip()
    return OCRResult(
        text=text,
        # Trust the user-provided source language. If none given, echo
        # the reader default ('hi' as most-likely non-English fallback).
        language=(source_language or "hi"),
        is_low_quality=len(text) < _LOW_QUALITY_THRESHOLD,
    )
