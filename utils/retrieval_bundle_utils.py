"""
Utilities for Phase 2 retrieval bundle compatibility.

These helpers keep the new retrieval_bundle contract and the legacy
retrieval_context view usable at the same time while the workflow is migrating.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Set


def is_retrieval_bundle(data: Any) -> bool:
    """Return True when the payload looks like a retrieval bundle."""
    return isinstance(data, dict) and any(
        key in data
        for key in ("atomic_modules", "subflow_templates", "system_patterns", "style_guides")
    )


def load_structured_payload(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load a structured payload from Chroma metadata.

    Phase 1 atomic modules store the full schema in `json_schema`.
    Phase 2 assets store the full payload in `payload_json`.
    """
    if not isinstance(metadata, dict):
        return {}

    raw_payload = metadata.get("payload_json")
    if isinstance(raw_payload, str) and raw_payload.strip():
        try:
            payload = json.loads(raw_payload)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            return {}

    raw_schema = metadata.get("json_schema")
    if isinstance(raw_schema, str) and raw_schema.strip():
        try:
            payload = json.loads(raw_schema)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            return {}

    return {}


def _as_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _is_subflow_template_doc(doc: Dict[str, Any]) -> bool:
    asset_type = str(doc.get("asset_type", "")).strip()
    template_json = doc.get("template_json", {})
    template_type = ""
    if isinstance(template_json, dict):
        template_type = str(template_json.get("type", "")).strip()

    return asset_type == "subflow_template" or template_type == "subflow"


def _normalize_compilable_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(doc)
    raw_template_json = normalized.get("template_json", {})
    raw_definition_id = ""
    if isinstance(raw_template_json, dict):
        raw_definition_id = str(raw_template_json.get("id") or "").strip()

    module_type = str(
        normalized.get("module_type")
        or normalized.get("template_id")
        or normalized.get("definition_id")
        or raw_definition_id
        or ""
    ).strip()
    if not module_type:
        return {}

    normalized["module_type"] = module_type
    if _is_subflow_template_doc(normalized):
        normalized["asset_type"] = "subflow_template"
        normalized.setdefault("template_id", module_type)
        normalized.setdefault("definition_id", raw_definition_id or normalized.get("template_id", module_type))
        template_json = normalized.get("template_json", {})
        if isinstance(template_json, dict):
            template_json = dict(template_json)
        else:
            template_json = {}
        template_json["type"] = "subflow"
        template_json["id"] = normalized["definition_id"]
        normalized["template_json"] = template_json
        if not normalized.get("name") and normalized.get("template_name"):
            normalized["name"] = normalized["template_name"]

    normalized.setdefault("name", "")
    normalized.setdefault("description", "")
    normalized.setdefault("category", "")
    normalized.setdefault("parameters_schema", {})
    normalized.setdefault("ports_definition", {})
    normalized.setdefault("template_json", {})
    normalized.setdefault("keywords", [])
    normalized.setdefault("usage_guides", [])
    return normalized


def get_atomic_modules(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return atomic module docs from bundle or legacy context."""
    if is_retrieval_bundle(bundle_or_context):
        return _as_list(bundle_or_context.get("atomic_modules", []))
    return [node for node in _as_list(bundle_or_context.get("relevant_nodes", [])) if not _is_subflow_template_doc(node)]


def get_subflow_templates(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return subflow template docs from bundle or mixed legacy context.

    The legacy branch intentionally tolerates historical mixed relevant_nodes.
    """
    if is_retrieval_bundle(bundle_or_context):
        return _as_list(bundle_or_context.get("subflow_templates", []))

    return [node for node in _as_list(bundle_or_context.get("relevant_nodes", [])) if _is_subflow_template_doc(node)]


def get_system_patterns(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if is_retrieval_bundle(bundle_or_context):
        return _as_list(bundle_or_context.get("system_patterns", []))
    return []


def get_style_guides(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if is_retrieval_bundle(bundle_or_context):
        return _as_list(bundle_or_context.get("style_guides", []))
    return []


def build_legacy_retrieval_context(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the official Phase 2 legacy view from retrieval_bundle.

    This output intentionally contains only the atomic_modules slice.
    """
    if not is_retrieval_bundle(bundle):
        return {
            "query": "",
            "relevant_nodes": [],
            "similar_cases": [],
            "metadata": {},
        }

    metadata = bundle.get("metadata", {}) if isinstance(bundle.get("metadata"), dict) else {}
    query_variants = metadata.get("query_variants", [])
    if not isinstance(query_variants, list):
        query_variants = []

    return {
        "query": metadata.get("query_text", ""),
        "relevant_nodes": _as_list(bundle.get("atomic_modules", [])),
        "similar_cases": [],
        "metadata": {
            "retrieved_count": int(metadata.get("retrieved_atomic_count", 0) or 0),
            "avg_confidence_score": float(metadata.get("avg_atomic_score", 0.0) or 0.0),
            "intent": metadata.get("intent", "general_query"),
            "detected_operations": metadata.get("detected_operations", []),
            "query_variants_used": len(query_variants),
        },
    }


def build_compilable_doc_map(bundle_or_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build the shared compilable doc map.

    Bundle mode aggregates atomic_modules + subflow_templates.
    Legacy mode keeps compatibility with historical mixed relevant_nodes.
    """
    doc_map: Dict[str, Dict[str, Any]] = {}

    if is_retrieval_bundle(bundle_or_context):
        candidate_docs = get_atomic_modules(bundle_or_context) + get_subflow_templates(bundle_or_context)
    else:
        candidate_docs = _as_list(bundle_or_context.get("relevant_nodes", []))

    for doc in candidate_docs:
        normalized = _normalize_compilable_doc(doc)
        module_type = normalized.get("module_type", "")
        if module_type:
            doc_map[module_type] = normalized

    return doc_map


def build_allowed_module_types(bundle_or_context: Dict[str, Any]) -> Set[str]:
    """Return the module_type whitelist for Planning validation."""
    return set(build_compilable_doc_map(bundle_or_context).keys())
