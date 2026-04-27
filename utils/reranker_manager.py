"""Cross-Encoder reranker 管理器。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple
from urllib import request
from urllib.error import HTTPError, URLError

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


class SiliconFlowReranker:
    """硅基流动 rerank API 适配器，保持内部 score_pairs 接口不变。"""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str,
        timeout_s: float = 20,
    ) -> None:
        if not api_key:
            raise ValueError("SILICONFLOW_API_KEY 未配置")
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = (base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        self.timeout_s = max(1.0, float(timeout_s or 20))

    def score_pairs(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        if not pairs:
            return []

        grouped: Dict[str, List[tuple[int, str]]] = {}
        for index, pair in enumerate(pairs):
            query, document = pair
            grouped.setdefault(str(query or ""), []).append((index, str(document or "")))

        scores = [0.0] * len(pairs)
        for query, indexed_documents in grouped.items():
            documents = [document for _, document in indexed_documents]
            response = self._create_rerank(query=query, documents=documents)
            local_scores = self._scores_from_response(response, len(documents))
            for (original_index, _), score in zip(indexed_documents, local_scores):
                scores[original_index] = score
        return scores

    def _create_rerank(self, *, query: str, documents: List[str]) -> Dict[str, Any]:
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
            "return_documents": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/rerank",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"SiliconFlow rerank 请求失败: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"SiliconFlow rerank 请求失败: {exc}") from exc

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("SiliconFlow rerank 返回了非 JSON 响应") from exc
        if not isinstance(data, dict):
            raise RuntimeError("SiliconFlow rerank 返回结构无效")
        return data

    @staticmethod
    def _scores_from_response(response: Dict[str, Any], expected_count: int) -> List[float]:
        scores = [0.0] * expected_count
        results = response.get("results", [])
        if not isinstance(results, list):
            raise RuntimeError("SiliconFlow rerank 响应缺少 results")
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
                score = float(item.get("relevance_score", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if 0 <= index < expected_count:
                scores[index] = score
        return scores


class RerankerManager:
    """按配置创建 reranker，测试可直接注入 fake scorer。"""

    @staticmethod
    def get_reranker(provider: str | None = None, model: str | None = None, **kwargs: Any):
        provider = (provider or config.RETRIEVAL_RERANKER_PROVIDER or "bge").strip()
        model_name = (model or config.RETRIEVAL_RERANKER_MODEL).strip()
        batch_size = int(kwargs.get("batch_size", config.RETRIEVAL_RERANK_BATCH_SIZE) or 16)
        if provider in {"bge", "sentence-transformers", "cross-encoder"}:
            return CrossEncoderReranker(model_name=model_name, batch_size=batch_size)
        if provider in {"siliconflow", "silicon-flow"}:
            return SiliconFlowReranker(
                model_name=model_name,
                api_key=kwargs.get("api_key", config.SILICONFLOW_API_KEY),
                base_url=kwargs.get("base_url", config.SILICONFLOW_BASE_URL),
                timeout_s=kwargs.get("timeout_s", config.RETRIEVAL_RERANK_TIMEOUT_S),
            )
        raise ValueError(f"不支持的 reranker 提供商: {provider}")
