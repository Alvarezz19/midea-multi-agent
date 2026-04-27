"""Retrieval 候选重排工具。"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _asset_id(candidate: Dict[str, Any], asset_type: str) -> str:
    if asset_type == "system_pattern":
        return str(candidate.get("pattern_id", "") or "").strip()
    return str(
        candidate.get("template_id")
        or candidate.get("module_type")
        or candidate.get("definition_id")
        or ""
    ).strip()


def build_candidate_text(candidate: Dict[str, Any], asset_type: str) -> str:
    """构造短文本卡片，避免把完整 flow body 送入 reranker。"""

    if asset_type == "system_pattern":
        pages = candidate.get("required_pages", [])
        page_labels: List[str] = []
        if isinstance(pages, list):
            for page in pages[:6]:
                if isinstance(page, dict):
                    label = str(page.get("label", "") or page.get("page_key", "")).strip()
                else:
                    label = str(page or "").strip()
                if label:
                    page_labels.append(label)
        fragments = [
            str(candidate.get("pattern_id", "") or ""),
            str(candidate.get("pattern_name", "") or ""),
            str(candidate.get("system_type", "") or ""),
            str(candidate.get("description", "") or ""),
            " ".join(page_labels),
        ]
    else:
        ports = candidate.get("ports_definition", {})
        port_labels: List[str] = []
        if isinstance(ports, dict):
            for direction in ("inputs", "outputs"):
                for port in (ports.get(direction, []) or [])[:6]:
                    if isinstance(port, dict):
                        label = str(port.get("label", "") or port.get("name", "")).strip()
                        if label:
                            port_labels.append(label)
        fragments = [
            str(candidate.get("template_id", "") or candidate.get("module_type", "") or ""),
            str(candidate.get("template_name", "") or candidate.get("name", "") or ""),
            str(candidate.get("template_role", "") or ""),
            str(candidate.get("system_type", "") or ""),
            str(candidate.get("description", "") or ""),
            " ".join(port_labels),
        ]
    return " ".join(fragment.strip() for fragment in fragments if fragment and fragment.strip())[:1200]


def rerank_retrieval_candidates(
    candidates: Sequence[Dict[str, Any]],
    *,
    query: str,
    scorer: Any,
    asset_type: str,
    top_n: int = 50,
) -> Dict[str, Any]:
    """只重排已召回候选；scorer 失败时保留原排序。"""

    original = [dict(item) for item in candidates if isinstance(item, dict)]
    if not original:
        return {
            "candidates": [],
            "fallback_used": False,
            "fallback_reason": "",
            "candidate_count": 0,
        }

    limited = original[: max(1, int(top_n or len(original)))]
    tail = original[len(limited):]
    pairs: List[Tuple[str, str]] = [
        (query, build_candidate_text(candidate, asset_type))
        for candidate in limited
    ]

    try:
        scores = scorer.score_pairs(pairs)
        if len(scores) != len(limited):
            raise ValueError("reranker score count mismatch")
    except Exception as exc:
        for index, candidate in enumerate(original, start=1):
            candidate["rank"] = index
        return {
            "candidates": original,
            "fallback_used": True,
            "fallback_reason": str(exc),
            "candidate_count": len(original),
        }

    reranked: List[Dict[str, Any]] = []
    for candidate, reranker_score in zip(limited, scores):
        item = dict(candidate)
        vector_score = _safe_float(item.get("similarity_score", item.get("vector_score", 0.0)))
        reranker_score = _safe_float(reranker_score)
        item["vector_score"] = vector_score
        item["reranker_score"] = reranker_score
        item["final_score"] = reranker_score * 0.5 + vector_score * 0.5
        item["asset_id"] = _asset_id(item, asset_type)
        item["asset_type"] = asset_type
        reranked.append(item)

    reranked.sort(key=lambda item: item.get("final_score", 0.0), reverse=True)
    merged = reranked + tail
    for index, candidate in enumerate(merged, start=1):
        candidate["rank"] = index
    return {
        "candidates": merged,
        "fallback_used": False,
        "fallback_reason": "",
        "candidate_count": len(original),
    }
