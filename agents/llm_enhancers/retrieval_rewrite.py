"""Retrieval 节点的可选 LLM 查询改写增强器。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class AssetQuerySpec(BaseModel):
    """按资产类型拆分的检索查询。"""

    asset_type: str = ""
    subsystem_id: str = ""
    subsystem_type: str = ""
    intent: str = ""
    query: str = ""
    must_match_terms: List[str] = Field(default_factory=list)
    port_roles: List[str] = Field(default_factory=list)


class RetrievalRewriteResult(BaseModel):
    """检索查询改写结果。"""

    query_variants: List[str] = Field(default_factory=list)
    template_queries: List[str] = Field(default_factory=list)
    pattern_queries: List[str] = Field(default_factory=list)
    atomic_queries: List[str] = Field(default_factory=list)
    asset_queries: List[AssetQuerySpec] = Field(default_factory=list)
    category_l1: str = ""
    normalized_terms: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _stringify_list_items(values: Any) -> List[str]:
    """兼容真实 LLM 将字符串列表项输出成对象的情况。"""

    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for item in values:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("query")
                or item.get("term")
                or item.get("type")
                or item.get("message")
                or item.get("reason")
                or item.get("text")
                or ""
            ).strip()
            if not text:
                text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


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
    if isinstance(payload, dict):
        payload = dict(payload)
        for key in ("query_variants", "template_queries", "pattern_queries", "atomic_queries", "normalized_terms", "risk_flags"):
            payload[key] = _stringify_list_items(payload.get(key, []))
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
- 基于用户需求、analysis_result 和 requirement_hint，按资产类型生成检索查询。
- system_pattern 查询关注目标 flows_*.json 形态、页签、标准对象组和完整 body。
- subflow_template 查询按子系统拆分，必须体现端口语义、控制对象、反馈/设定/输出、联锁和模式。
- atomic_module 查询关注 PID、limit、switch、delay、quote、通讯输出等原子模块。
- 只能输出查询文本、术语和风险标记，不允许输出最终 flows JSON。
- 不允许发明 template_id、pattern_id 或 module_type。
- 不确定时写入 risk_flags，不要强行选择资产。
- 对复杂 AHU 请求不能返回空查询；至少输出 1 条 pattern 查询和每个显式子系统 1 条 template 查询。"""

        user_template = """用户需求：
{query}

analysis_result：
{analysis_json}

requirement_hint：
{requirement_json}

请只输出合法 JSON 对象，字段符合 RetrievalRewriteResult。优先填写 asset_queries；同时可填写 pattern_queries、template_queries、atomic_queries。每一类查询都应简短、可检索，列表总量控制在 {max_queries} 条以内。"""
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    def _invoke_json(self, messages: Any) -> Any:
        llm = self.llm
        if self.provider.lower() == "deepseek" and hasattr(llm, "bind"):
            llm = llm.bind(response_format={"type": "json_object"})
        return llm.invoke(messages)

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
        asset_queries = self._normalize_asset_queries(payload.get("asset_queries", []), max_items)
        asset_query_texts = [item["query"] for item in asset_queries if item.get("query")]
        pattern_asset_queries = [
            item["query"]
            for item in asset_queries
            if item.get("asset_type") in {"system_pattern", "pattern"} and item.get("query")
        ]
        template_asset_queries = [
            item["query"]
            for item in asset_queries
            if item.get("asset_type") in {"subflow_template", "template"} and item.get("query")
        ]
        atomic_asset_queries = [
            item["query"]
            for item in asset_queries
            if item.get("asset_type") in {"atomic_module", "atomic"} and item.get("query")
        ]
        query_variants = self._clean_list(payload.get("query_variants", []) + asset_query_texts, max_items)
        remaining = max(0, max_items - len(query_variants))
        template_queries = self._clean_list(payload.get("template_queries", []) + template_asset_queries, remaining)
        remaining = max(0, max_items - len(query_variants) - len(template_queries))
        pattern_queries = self._clean_list(payload.get("pattern_queries", []) + pattern_asset_queries, remaining)
        remaining = max(0, max_items - len(query_variants) - len(template_queries) - len(pattern_queries))
        atomic_queries = self._clean_list(payload.get("atomic_queries", []) + atomic_asset_queries, remaining)
        return {
            "query_variants": query_variants,
            "template_queries": template_queries,
            "pattern_queries": pattern_queries,
            "atomic_queries": atomic_queries,
            "asset_queries": asset_queries,
            "category_l1": self._clean_text(payload.get("category_l1", "")),
            "normalized_terms": self._clean_list(payload.get("normalized_terms", []), max_items),
            "risk_flags": self._clean_list(payload.get("risk_flags", []), max_items),
        }

    def _normalize_asset_queries(self, values: Any, max_items: int) -> List[Dict[str, Any]]:
        if not isinstance(values, list):
            return []
        result: List[Dict[str, Any]] = []
        seen = set()
        for item in values:
            if not isinstance(item, dict):
                continue
            asset_type = self._clean_text(item.get("asset_type", "")).lower()
            query = self._clean_text(item.get("query", ""))
            if asset_type not in {"system_pattern", "pattern", "subflow_template", "template", "atomic_module", "atomic"}:
                continue
            if not query:
                continue
            key = (asset_type, query)
            if key in seen:
                continue
            result.append(
                {
                    "asset_type": asset_type,
                    "subsystem_id": self._clean_text(item.get("subsystem_id", "")),
                    "subsystem_type": self._clean_text(item.get("subsystem_type", "")),
                    "intent": self._clean_text(item.get("intent", "")),
                    "query": query,
                    "must_match_terms": self._clean_list(item.get("must_match_terms", []), 8),
                    "port_roles": self._clean_list(item.get("port_roles", []), 8),
                }
            )
            seen.add(key)
            if len(result) >= max_items:
                break
        return result

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
            if self.provider.lower() == "deepseek":
                raise RuntimeError("structured_output_skipped_for_deepseek_json_mode")
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
                response = self._invoke_json(messages)
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
            + len(normalized["atomic_queries"])
        )
        diagnostics["asset_query_count"] = len(normalized.get("asset_queries", []) or [])
        return {
            "rewrite": normalized,
            "diagnostics": diagnostics,
        }
