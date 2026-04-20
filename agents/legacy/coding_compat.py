"""Legacy compiler compatibility helpers."""
from __future__ import annotations

from typing import Any, Callable, Dict

from utils.retrieval_bundle_utils import build_bundle_doc_map, build_legacy_doc_map, is_retrieval_bundle


def build_compat_doc_map(retrieval_input: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build the legacy-tolerant doc map for direct compiler callers."""
    if is_retrieval_bundle(retrieval_input):
        return build_bundle_doc_map(retrieval_input)
    return build_legacy_doc_map(retrieval_input)


def compile_graph_compat(
    compile_with_doc_map: Callable[[Dict[str, Any], Dict[str, Dict[str, Any]]], Dict[str, Any]],
    *,
    assembled_graph_ir: Dict[str, Any],
    retrieval_input: Dict[str, Any],
) -> Dict[str, Any]:
    """Compile using the compat doc-map builder kept for legacy callers."""
    doc_map = build_compat_doc_map(retrieval_input)
    return compile_with_doc_map(assembled_graph_ir, doc_map)


def generate_json_compat(
    compile_with_doc_map: Callable[[Dict[str, Any], Dict[str, Dict[str, Any]]], Dict[str, Any]],
    *,
    assembled_graph_ir: Dict[str, Any],
    retrieval_input: Dict[str, Any],
) -> str:
    """Legacy JSON-only view built on top of the compat compile surface."""
    artifact = compile_graph_compat(
        compile_with_doc_map,
        assembled_graph_ir=assembled_graph_ir,
        retrieval_input=retrieval_input,
    )
    return artifact["json_text"]
