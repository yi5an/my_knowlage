"""Dedupe-key computation for investment raw items.

Per doc 04 §4.1: ``dedupe_key = sha256(source_type + stable_external_id + source_url)``.
``stable_external_id`` comes from the source's most stable native id:

- SEC: accessionNumber
- RSS: guid, else link
- Federal Reserve RSS: guid / link
- BLS / FRED: series_id + observation_date + value
- HKEX / CNINFO: announcement_id, else PDF URL
"""

from __future__ import annotations

import hashlib


def compute_dedupe_key(source_type: str, external_id: str, url: str) -> str:
    """Return a stable hex digest for an investment item.

    ``source_type`` is joined (not concatenated naively) so that two different
    source types cannot collide on the same external id + url.
    """
    raw = f"{source_type}|{external_id}|{url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
