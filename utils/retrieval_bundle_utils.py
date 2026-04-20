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


def _ensure_bundle_payload(retrieval_bundle: Dict[str, Any] | None) -> Dict[str, Any]:
    if retrieval_bundle is None:
        return {}
    if not isinstance(retrieval_bundle, dict):
        raise ValueError("retrieval_bundle must be a dict.")
    if not retrieval_bundle:
        return {}
    if not is_retrieval_bundle(retrieval_bundle):
        raise ValueError("Formal retrieval helpers require a retrieval_bundle payload.")
    return retrieval_bundle


def _ensure_legacy_context_payload(retrieval_context: Dict[str, Any] | None) -> Dict[str, Any]:
    if retrieval_context is None:
        return {}
    if not isinstance(retrieval_context, dict):
        raise ValueError("retrieval_context must be a dict.")
    if not retrieval_context:
        return {}
    if is_retrieval_bundle(retrieval_context):
        raise ValueError("Legacy retrieval helpers require a retrieval_context payload.")
    return retrieval_context


def get_bundle_atomic_modules(retrieval_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return atomic module docs from formal retrieval_bundle only."""
    bundle = _ensure_bundle_payload(retrieval_bundle)
    return _as_list(bundle.get("atomic_modules", []))


def get_bundle_subflow_templates(retrieval_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return subflow template docs from formal retrieval_bundle only."""
    bundle = _ensure_bundle_payload(retrieval_bundle)
    return _as_list(bundle.get("subflow_templates", []))


def get_bundle_system_patterns(retrieval_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return system pattern docs from formal retrieval_bundle only."""
    bundle = _ensure_bundle_payload(retrieval_bundle)
    return _as_list(bundle.get("system_patterns", []))


def get_bundle_style_guides(retrieval_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return style guide docs from formal retrieval_bundle only."""
    bundle = _ensure_bundle_payload(retrieval_bundle)
    return _as_list(bundle.get("style_guides", []))


def get_legacy_atomic_modules(retrieval_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return atomic module docs from legacy retrieval_context only."""
    context = _ensure_legacy_context_payload(retrieval_context)
    return [node for node in _as_list(context.get("relevant_nodes", [])) if not _is_subflow_template_doc(node)]


def get_legacy_subflow_templates(retrieval_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return subflow template docs from legacy retrieval_context only.

    The legacy branch intentionally tolerates historical mixed relevant_nodes.
    """
    context = _ensure_legacy_context_payload(retrieval_context)
    return [node for node in _as_list(context.get("relevant_nodes", [])) if _is_subflow_template_doc(node)]


def get_atomic_modules(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compatibility dispatcher for retrieval_bundle / retrieval_context callers."""
    if is_retrieval_bundle(bundle_or_context):
        return get_bundle_atomic_modules(bundle_or_context)
    return get_legacy_atomic_modules(bundle_or_context)


def get_subflow_templates(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compatibility dispatcher for retrieval_bundle / retrieval_context callers."""
    if is_retrieval_bundle(bundle_or_context):
        return get_bundle_subflow_templates(bundle_or_context)
    return get_legacy_subflow_templates(bundle_or_context)


def get_system_patterns(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compatibility dispatcher for retrieval_bundle / retrieval_context callers."""
    if is_retrieval_bundle(bundle_or_context):
        return get_bundle_system_patterns(bundle_or_context)
    return []


def get_style_guides(bundle_or_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compatibility dispatcher for retrieval_bundle / retrieval_context callers."""
    if is_retrieval_bundle(bundle_or_context):
        return get_bundle_style_guides(bundle_or_context)
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
        "relevant_nodes": get_bundle_atomic_modules(bundle),
        "similar_cases": [],
        "metadata": {
            "retrieved_count": int(metadata.get("retrieved_atomic_count", 0) or 0),
            "avg_confidence_score": float(metadata.get("avg_atomic_score", 0.0) or 0.0),
            "intent": metadata.get("intent", "general_query"),
            "detected_operations": metadata.get("detected_operations", []),
            "query_variants_used": len(query_variants),
        },
    }


def build_bundle_doc_map(retrieval_bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build the formal compilable doc map from retrieval_bundle only."""
    bundle = _ensure_bundle_payload(retrieval_bundle)
    doc_map: Dict[str, Dict[str, Any]] = {}

    candidate_docs = get_bundle_atomic_modules(bundle) + get_bundle_subflow_templates(bundle)
    for doc in candidate_docs:
        normalized = _normalize_compilable_doc(doc)
        module_type = normalized.get("module_type", "")
        if module_type:
            doc_map[module_type] = normalized

    return doc_map


def build_legacy_doc_map(retrieval_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build the legacy compilable doc map from retrieval_context only."""
    context = _ensure_legacy_context_payload(retrieval_context)
    doc_map: Dict[str, Dict[str, Any]] = {}

    for doc in _as_list(context.get("relevant_nodes", [])):
        normalized = _normalize_compilable_doc(doc)
        module_type = normalized.get("module_type", "")
        if module_type:
            doc_map[module_type] = normalized

    return doc_map


def build_compilable_doc_map(bundle_or_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Compatibility dispatcher for retrieval_bundle / retrieval_context callers.
    """
    if is_retrieval_bundle(bundle_or_context):
        return build_bundle_doc_map(bundle_or_context)
    return build_legacy_doc_map(bundle_or_context)


def build_bundle_allowed_module_types(retrieval_bundle: Dict[str, Any]) -> Set[str]:
    """Return the formal module_type whitelist from retrieval_bundle only."""
    return set(build_bundle_doc_map(retrieval_bundle).keys())


def build_legacy_allowed_module_types(retrieval_context: Dict[str, Any]) -> Set[str]:
    """Return the legacy module_type whitelist from retrieval_context only."""
    return set(build_legacy_doc_map(retrieval_context).keys())


def build_allowed_module_types(bundle_or_context: Dict[str, Any]) -> Set[str]:
    """Compatibility dispatcher for retrieval_bundle / retrieval_context callers."""
    if is_retrieval_bundle(bundle_or_context):
        return build_bundle_allowed_module_types(bundle_or_context)
    return build_legacy_allowed_module_types(bundle_or_context)
