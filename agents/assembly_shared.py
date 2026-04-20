"""Shared assembly helpers used by both legacy and formal assembly paths."""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from utils.graph_ir import SubflowDefinitionIR, SubflowPortIR
from utils.retrieval_bundle_utils import build_bundle_doc_map, build_legacy_doc_map, is_retrieval_bundle


class AssemblySharedMixin:
    """Shared helpers for converting retrieval docs into Graph IR fragments."""

    DEFAULT_PAGE_ID = "page_control"
    DEFAULT_PAGE_LABEL = "自动生成流程"

    @staticmethod
    def _normalize_template(template_raw: Any) -> Dict[str, Any]:
        if isinstance(template_raw, list):
            if template_raw and isinstance(template_raw[0], dict):
                return copy.deepcopy(template_raw[0])
            return {}
        if isinstance(template_raw, dict):
            return copy.deepcopy(template_raw)
        return {}

    @staticmethod
    def _build_formal_doc_map(retrieval_bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return build_bundle_doc_map(retrieval_bundle)

    @staticmethod
    def _build_compat_doc_map(retrieval_input: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        if is_retrieval_bundle(retrieval_input):
            return build_bundle_doc_map(retrieval_input)
        return build_legacy_doc_map(retrieval_input)

    def _build_subflow_definition(
        self,
        module_type: str,
        module_doc: Optional[Dict[str, Any]],
    ) -> Optional[SubflowDefinitionIR]:
        if not module_doc:
            return None

        raw_definition = self._normalize_template(module_doc.get("template_json", {}))
        if raw_definition.get("type") != "subflow":
            return None

        template_id = str(module_doc.get("template_id") or module_type).strip()
        definition_id = str(module_doc.get("definition_id") or raw_definition.get("id") or template_id).strip()
        name = str(raw_definition.get("name") or module_doc.get("template_name") or module_doc.get("name") or template_id).strip()
        in_ports = raw_definition.get("in", []) or []
        out_ports = raw_definition.get("out", []) or []

        return SubflowDefinitionIR(
            template_id=template_id,
            definition_id=definition_id,
            name=name,
            inputs=len(in_ports) or int(raw_definition.get("inputs", 0) or 0),
            outputs=len(out_ports) or int(raw_definition.get("outputs", 0) or 0),
            in_ports=[
                SubflowPortIR(
                    port_index=index,
                    name=str(port.get("name", "")),
                    x=int(port.get("x", 0) or 0),
                    y=int(port.get("y", 0) or 0),
                )
                for index, port in enumerate(in_ports)
            ],
            out_ports=[
                SubflowPortIR(
                    port_index=index,
                    name=str(port.get("name", "")),
                    x=int(port.get("x", 0) or 0),
                    y=int(port.get("y", 0) or 0),
                )
                for index, port in enumerate(out_ports)
            ],
            raw_definition=raw_definition,
        )


__all__ = ["AssemblySharedMixin"]
