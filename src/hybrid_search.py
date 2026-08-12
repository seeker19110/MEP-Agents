"""Hybrid standards search: vector + keyword RRF (Phase D)."""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(
    r"\b(?:TCVN|QCVN|TCXD|NFPA|ASHRAE|IEC|BS\s?EN|EN)\s*[\d./:-]+",
    re.IGNORECASE,
)


def _keyword_hits(query: str, k: int = 8) -> list[tuple[str, str, float]]:
    try:
        from src.tools import _load_offline_corpus, _tokenize
    except Exception as e:
        logger.debug("keyword corpus unavailable: %s", e)
        return []
    standards_dir = os.environ.get("STANDARDS_DIR", "data/standards")
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    chunks = _load_offline_corpus(standards_dir)
    scored = []
    for fname, para in chunks:
        para_tokens = _tokenize(para)
        if not para_tokens:
            continue
        overlap = len(query_tokens & para_tokens)
        if overlap == 0:
            continue
        score = overlap / len(query_tokens | para_tokens)
        codes = _CODE_RE.findall(query)
        if codes and any(c.upper().replace(" ", "") in para.upper().replace(" ", "") for c in codes):
            score += 0.35
        scored.append((fname, para, score))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:k]


def _vector_hits(query: str, k: int = 8) -> list[tuple[str, str, float]]:
    try:
        from src.vectorstore import search_standards_with_scores
        pairs = search_standards_with_scores(query, k=k)
    except Exception as e:
        logger.debug("vector hits failed: %s", e)
        return []
    out = []
    for doc, score in pairs:
        text = getattr(doc, "page_content", "") or ""
        src = (getattr(doc, "metadata", None) or {}).get("source", "vector")
        try:
            sim = 1.0 / (1.0 + float(score))
        except Exception:
            sim = 0.5
        out.append((str(src), text, sim))
    return out


def reciprocal_rank_fusion(ranked_lists: list, *, k: int = 5, rrf_k: int = 60) -> list[tuple[str, str, float]]:
    scores: dict[str, float] = {}
    payload: dict[str, tuple[str, str]] = {}
    for ranked in ranked_lists:
        for rank, (src, text, _s) in enumerate(ranked, start=1):
            key = (text or "")[:240]
            if not key.strip():
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
            payload[key] = (src, text)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    return [(payload[key][0], payload[key][1], sc) for key, sc in ordered]


def hybrid_search_standards(query: str, k: int = 5) -> list[tuple[str, str, float]]:
    q = (query or "").strip()
    if not q:
        return []
    kw = _keyword_hits(q, k=max(8, k * 2))
    vec = []
    try:
        vec = _vector_hits(q, k=max(8, k * 2))
    except Exception as e:
        logger.info("hybrid: vector path skipped (%s)", e)
    if not vec and not kw:
        return []
    if not vec:
        return [(s, t, sc) for s, t, sc in kw[:k]]
    if not kw:
        return vec[:k]
    return reciprocal_rank_fusion([vec, kw], k=k)


def format_hybrid_results(query: str, hits: list[tuple[str, str, float]]) -> str:
    if not hits:
        return f"Không tìm thấy tiêu chuẩn khớp với '{query}'."
    lines = [f"Kết quả HYBRID (vector + từ khóa) cho '{query}':\n"]
    for i, (src, text, sc) in enumerate(hits, 1):
        lines.append(f"--- Trích đoạn {i} (Nguồn: {src}, score={sc:.4f}) ---")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)
