"""Cross-Encoder reranker 管理器。"""
from __future__ import annotations

from typing import Any, List, Sequence, Tuple

import config


class CrossEncoderReranker:
    """sentence-transformers CrossEncoder 的轻量包装。"""

    def __init__(self, model_name: str, batch_size: int = 16) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self.batch_size = max(1, int(batch_size or 16))
        self.model = CrossEncoder(model_name)

    def score_pairs(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        if not pairs:
            return []
        raw_scores = self.model.predict(list(pairs), batch_size=self.batch_size)
        return [float(score) for score in raw_scores]


class RerankerManager:
    """按配置创建 reranker，测试可直接注入 fake scorer。"""

    @staticmethod
    def get_reranker(provider: str | None = None, model: str | None = None, **kwargs: Any):
        provider = (provider or config.RETRIEVAL_RERANKER_PROVIDER or "bge").strip()
        model_name = (model or config.RETRIEVAL_RERANKER_MODEL).strip()
        batch_size = int(kwargs.get("batch_size", config.RETRIEVAL_RERANK_BATCH_SIZE) or 16)
        if provider in {"bge", "sentence-transformers", "cross-encoder"}:
            return CrossEncoderReranker(model_name=model_name, batch_size=batch_size)
        raise ValueError(f"不支持的 reranker 提供商: {provider}")
