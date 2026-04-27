"""Retrieval 节点的可选 LLM 查询改写增强器。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class RetrievalRewriteResult(BaseModel):
    """检索查询改写结果。"""

    query_variants: List[str] = Field(default_factory=list)
    template_queries: List[str] = Field(default_factory=list)
    pattern_queries: List[str] = Field(default_factory=list)
    category_l1: str = ""
    normalized_terms: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _validate_payload(payload: Any) -> RetrievalRewriteResult:
    if isinstance(payload, RetrievalRewriteResult):
        return payload
    if isinstance(payload, list):
        query_variants: List[str] = []
        normalized_terms: List[str] = []
        risk_flags: List[str] = []
        for item in payload:
            if isinstance(item, str):
                query_variants.append(item)
                continue
            if not isinstance(item, dict):
                continue
            query_text = str(
                item.get("query")
                or item.get("text")
                or item.get("query_variant")
                or ""
            ).strip()
            if query_text:
                query_variants.append(query_text)
            terms = item.get("terms", item.get("normalized_terms", []))
            if isinstance(terms, list):
                normalized_terms.extend(str(term).strip() for term in terms if str(term).strip())
            item_risks = item.get("risk_flags", [])
            if isinstance(item_risks, list):
                risk_flags.extend(str(flag).strip() for flag in item_risks if str(flag).strip())
        payload = {
            "query_variants": query_variants,
            "normalized_terms": normalized_terms,
            "risk_flags": risk_flags,
        }
    if hasattr(RetrievalRewriteResult, "model_validate"):
        return RetrievalRewriteResult.model_validate(payload)
    return RetrievalRewriteResult.parse_obj(payload)


class RetrievalQueryRewriter:
    """只生成查询变体，不选择资产 ID。"""

    def __init__(self, llm: Any, provider: str = "", model: str = "", max_queries: int = 8) -> None:
        self.llm = llm
        self.provider = provider
        self.model = model
        self.max_queries = max(1, int(max_queries or 8))
        self.prompt = self._create_prompt()

    @staticmethod
    def _extract_json_text(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return stripped
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if json_match:
            return json_match.group(1).strip()
        obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
        if obj_match:
            return obj_match.group(1).strip()
        return stripped

    @staticmethod
    def _create_prompt() -> ChatPromptTemplate:
        system_prompt = """你是 AHU / 楼控资产检索查询改写器。

任务：
- 基于用户需求、analysis_result 和 requirement_hint，生成更适合检索原子模块、子流程模板、系统 pattern 的短查询。
- 只能输出查询文本、术语和风险标记，不允许输出最终 flows JSON。
- 不允许发明 template_id、pattern_id 或 module_type。
- 不确定时写入 risk_flags，不要强行选择资产。"""

        user_template = """用户需求：
{query}

analysis_result：
{analysis_json}

requirement_hint：
{requirement_json}

请输出 RetrievalRewriteResult，列表总量控制在 {max_queries} 条以内。"""
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    @staticmethod
    def _clean_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @classmethod
    def _clean_list(cls, value: Any, max_items: int) -> List[str]:
        if max_items <= 0:
            return []
        if not isinstance(value, list):
            return []
        result: List[str] = []
        seen = set()
        for item in value:
            text = cls._clean_text(item)
            if text and text not in seen:
                result.append(text)
                seen.add(text)
            if len(result) >= max_items:
                break
        return result

    def _normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        max_items = self.max_queries
        query_variants = self._clean_list(payload.get("query_variants", []), max_items)
        remaining = max(0, max_items - len(query_variants))
        template_queries = self._clean_list(payload.get("template_queries", []), remaining)
        remaining = max(0, max_items - len(query_variants) - len(template_queries))
        pattern_queries = self._clean_list(payload.get("pattern_queries", []), remaining)
        return {
            "query_variants": query_variants,
            "template_queries": template_queries,
            "pattern_queries": pattern_queries,
            "category_l1": self._clean_text(payload.get("category_l1", "")),
            "normalized_terms": self._clean_list(payload.get("normalized_terms", []), max_items),
            "risk_flags": self._clean_list(payload.get("risk_flags", []), max_items),
        }

    def rewrite(
        self,
        query: str,
        analysis_result: Dict[str, Any],
        requirement_hint: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """调用 LLM 改写查询；失败时返回 fallback 诊断。"""

        start = time.perf_counter()
        diagnostics: Dict[str, Any] = {
            "enabled": True,
            "provider": self.provider,
            "model": self.model,
            "structured_output_used": False,
            "llm_used": False,
            "fallback_used": False,
            "fallback_reason": "",
            "elapsed_ms": 0,
        }
        messages = self.prompt.format_messages(
            query=query,
            analysis_json=json.dumps(analysis_result or {}, ensure_ascii=False, sort_keys=True),
            requirement_json=json.dumps(requirement_hint or {}, ensure_ascii=False, sort_keys=True),
            max_queries=self.max_queries,
        )

        try:
            structured_llm = self.llm.with_structured_output(
                RetrievalRewriteResult,
                method="function_calling",
            )
            response = structured_llm.invoke(messages)
            payload = _model_to_dict(_validate_payload(_model_to_dict(response)))
            diagnostics["structured_output_used"] = True
            diagnostics["llm_used"] = True
        except Exception as structured_error:
            try:
                response = self.llm.invoke(messages)
                raw = self._extract_json_text(getattr(response, "content", "") or "")
                payload = _model_to_dict(_validate_payload(json.loads(raw) if raw else {}))
                diagnostics["llm_used"] = True
                diagnostics["fallback_reason"] = f"structured_output_failed: {structured_error}"
            except Exception as parse_error:
                diagnostics["fallback_used"] = True
                diagnostics["fallback_reason"] = str(parse_error)
                diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return {
                    "rewrite": {},
                    "diagnostics": diagnostics,
                }

        normalized = self._normalize(payload)
        diagnostics["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        diagnostics["query_count"] = (
            len(normalized["query_variants"])
            + len(normalized["template_queries"])
            + len(normalized["pattern_queries"])
        )
        return {
            "rewrite": normalized,
            "diagnostics": diagnostics,
        }
