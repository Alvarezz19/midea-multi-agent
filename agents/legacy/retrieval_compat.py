"""Legacy retrieval compatibility helpers."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from utils.retrieval_bundle_utils import build_legacy_retrieval_context


def retrieve_legacy_context(
    retrieve_bundle: Callable[..., Dict[str, Any]],
    *,
    query: str,
    top_k: int = 10,
    category_filter: Optional[str] = None,
    similarity_threshold: float = 0.3,
    analysis_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project retrieval_bundle back into the legacy retrieval_context view."""
    bundle = retrieve_bundle(
        query=query,
        top_k=top_k,
        category_filter=category_filter,
        similarity_threshold=similarity_threshold,
        analysis_result=analysis_result,
    )
    context = build_legacy_retrieval_context(bundle)
    metadata = dict(context.get("metadata", {}))
    metadata["category_filter"] = category_filter
    context["metadata"] = metadata
    return context
