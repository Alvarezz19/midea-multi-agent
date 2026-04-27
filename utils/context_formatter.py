"""
Context formatting helpers for retrieval-backed agents.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from utils.retrieval_bundle_utils import (
    build_bundle_doc_map,
    get_bundle_atomic_modules,
    get_bundle_subflow_templates,
    get_bundle_system_patterns,
)


def _port_label(port: Dict[str, Any]) -> str:
    return str(port.get("label") or port.get("name") or "unnamed")


def _summarize_port_overview(ports_def: Dict[str, Any]) -> str:
    input_ports = ports_def.get("inputs", [])
    output_ports = ports_def.get("outputs", [])
    return f"{len(input_ports)} in -> {len(output_ports)} out"


def _summarize_param_keys(params_schema: Dict[str, Any]) -> str:
    if not params_schema:
        return "none"
    return ", ".join(params_schema.keys())


def _append_detail_block(lines: List[str], node: Dict[str, Any]) -> None:
    params_schema = node.get("parameters_schema", {})
    if params_schema:
        lines.append("    Parameters:")
        for key, info in params_schema.items():
            p_type = info.get("type", "unknown")
            p_default = info.get("default", "N/A")
            p_desc = info.get("description", "")
            constraint_parts = []
            if "minimum" in info:
                constraint_parts.append(f"min={info['minimum']}")
            if "maximum" in info:
                constraint_parts.append(f"max={info['maximum']}")
            if "enum" in info:
                constraint_parts.append(f"choices={info['enum']}")
            constraint_str = f" [{', '.join(constraint_parts)}]" if constraint_parts else ""
            lines.append(f"      - {key} ({p_type}, default={p_default}){constraint_str}: {p_desc}")

    ports_def = node.get("ports_definition", {})
    if ports_def:
        input_ports = ports_def.get("inputs", [])
        output_ports = ports_def.get("outputs", [])
        if input_ports:
            lines.append("    Inputs:")
            for port in input_ports:
                p_idx = port.get("index", 0)
                p_label = _port_label(port)
                p_type = port.get("type", "any")
                p_desc = port.get("description", "")
                p_cond = port.get("condition", "always")
                cond_str = f" (condition: {p_cond})" if p_cond != "always" else ""
                lines.append(f"      - [{p_idx}] {p_label} ({p_type}){cond_str}: {p_desc}")
        if output_ports:
            lines.append("    Outputs:")
            for port in output_ports:
                p_idx = port.get("index", 0)
                p_label = _port_label(port)
                p_type = port.get("type", "any")
                p_desc = port.get("description", "")
                p_cond = port.get("condition", "always")
                cond_str = f" (condition: {p_cond})" if p_cond != "always" else ""
                lines.append(f"      - [{p_idx}] {p_label} ({p_type}){cond_str}: {p_desc}")

    usage_guides = node.get("usage_guides", [])
    if usage_guides:
        lines.append("    Suggested use cases:")
        for guide in usage_guides:
            lines.append(f"      - {guide}")


def _append_summary_block(lines: List[str], node: Dict[str, Any]) -> None:
    params_schema = node.get("parameters_schema", {})
    ports_def = node.get("ports_definition", {})
    description = node.get("description", "No description")
    lines.append(f"    Description: {description}")
    lines.append(f"    Parameter keys: {_summarize_param_keys(params_schema)}")
    lines.append(f"    Port overview: {_summarize_port_overview(ports_def)}")


def format_docs_for_planner(
    retrieval_bundle: Dict[str, Any],
    detail_top_n: int = 5,
    max_modules: int = 8,
) -> str:
    """Format formal retrieval_bundle for planning-related callers."""
    atomic_modules = get_bundle_atomic_modules(retrieval_bundle)
    subflow_templates = get_bundle_subflow_templates(retrieval_bundle)
    system_patterns = get_bundle_system_patterns(retrieval_bundle)

    if not atomic_modules and not subflow_templates and not system_patterns:
        return "No retrieval candidates found."

    metadata = retrieval_bundle.get("metadata", {}) if isinstance(retrieval_bundle, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    query_text = metadata.get("query_text", "N/A")
    avg_score = metadata.get("avg_atomic_score", 0)
    retrieved_count = metadata.get("retrieved_atomic_count", len(atomic_modules))

    lines: List[str] = []
    lines.append("Retrieval Summary")
    lines.append(f"\nQuery: {query_text}")
    lines.append("Stats:")
    lines.append(f"  - Atomic modules: {retrieved_count}")
    lines.append(f"  - Subflow templates: {len(subflow_templates)}")
    lines.append(f"  - System patterns: {len(system_patterns)}")
    lines.append(f"  - Avg atomic similarity: {float(avg_score or 0):.3f}")

    if metadata.get("detected_operations"):
        lines.append(f"  - Detected operations: {', '.join(metadata['detected_operations'])}")
    if metadata.get("intent"):
        lines.append(f"  - Intent: {metadata['intent']}")

    if system_patterns:
        lines.append("\nSystem Pattern Hints:")
        for pattern in system_patterns[:3]:
            pattern_name = pattern.get("pattern_name") or pattern.get("name") or pattern.get("pattern_id", "Unknown")
            required_pages = pattern.get("required_pages", [])
            optional_pages = pattern.get("optional_pages", [])
            page_summary = []
            if required_pages:
                labels = [page.get("label") or page.get("page_key", "") for page in required_pages[:5]]
                page_summary.append("required=" + ", ".join(labels))
            if optional_pages:
                labels = [page.get("label") or page.get("page_key", "") for page in optional_pages[:5]]
                page_summary.append("optional=" + ", ".join(labels))
            lines.append(f"  - {pattern_name}: {'; '.join(page_summary) if page_summary else 'no page summary'}")

    if subflow_templates:
        lines.append("\nSubflow Template Candidates:")
        for template in subflow_templates[:5]:
            name = template.get("template_name") or template.get("name") or template.get("template_id", "Unknown")
            module_type = template.get("module_type") or template.get("template_id", "Unknown")
            category = template.get("category", "Unknown")
            score = float(template.get("similarity_score", 0) or 0)
            lines.append(f"  - {name} ({module_type}) | category={category} | score={score:.3f}")

    lines.append("\nAtomic Module Candidates:")
    relevant_nodes = atomic_modules[:max_modules]
    for index, node in enumerate(relevant_nodes, start=1):
        rank = node.get("rank", index)
        name = node.get("name", "Unknown")
        module_type = node.get("module_type", "Unknown")
        category = node.get("category", "Unknown")
        similarity = float(node.get("similarity_score", 0) or 0)

        lines.append(f"\n[{rank}] {name}")
        lines.append(f"    Type: {module_type}")
        lines.append(f"    Category: {category}")
        lines.append(f"    Similarity: {similarity:.3f}")

        if index <= detail_top_n:
            _append_detail_block(lines, node)
        else:
            _append_summary_block(lines, node)

        matched_query = node.get("matched_query")
        if matched_query and matched_query != query_text:
            lines.append(f"    Matched query: {matched_query}")
        lines.append("")

    lines.append("Planning Notes:")
    top_similarity = float(relevant_nodes[0].get("similarity_score", 0) or 0) if relevant_nodes else 0.0
    if subflow_templates:
        lines.append("  Prefer reusable subflow templates before falling back to atomic assembly.")
    if system_patterns:
        lines.append("  Use system patterns as layout and page hints only, not as hard output schema.")
    if top_similarity > 0.8:
        lines.append("  Atomic candidates are strong; prefer the top-ranked modules when templates are insufficient.")
    elif top_similarity > 0.6:
        lines.append("  Atomic candidates are moderate; combine modules carefully.")
    else:
        lines.append("  Atomic candidates are weak; expect more composition work.")

    categories: Dict[str, int] = {}
    for node in relevant_nodes:
        category = str(node.get("category", "Unknown")).split("/")[0]
        categories[category] = categories.get(category, 0) + 1
    if categories:
        cat_summary = ", ".join(f"{key}({value})" for key, value in categories.items())
        lines.append(f"  Category distribution: {cat_summary}")

    return "\n".join(lines)


def format_docs_for_coding(retrieval_bundle: Dict[str, Any], selected_modules: List[str]) -> str:
    """Prepare detailed module information from formal retrieval_bundle."""
    doc_map = build_bundle_doc_map(retrieval_bundle)
    if not doc_map:
        return "No relevant module information found."

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append("Module Technical Specification")
    lines.append("=" * 80)

    for module_type in selected_modules:
        module_info = doc_map.get(module_type)
        if not module_info:
            lines.append(f"\n[Missing] module_type={module_type}")
            continue

        lines.append(f"\n{'=' * 80}")
        lines.append(f"Module: {module_info.get('name') or module_type} ({module_type})")
        lines.append(f"{'=' * 80}")
        lines.append(f"\nDescription: {module_info.get('description', 'N/A')}")
        lines.append(f"Category: {module_info.get('category', 'N/A')}")

        params_schema = module_info.get("parameters_schema", {})
        if params_schema:
            lines.append("\nParameters:")
            for key, info in params_schema.items():
                if key in {"x", "y", "wires", "id", "z"}:
                    continue
                param_type = info.get("type", "unknown")
                param_desc = info.get("description", "")
                param_default = info.get("default", "N/A")
                param_required = bool(info.get("required", False))
                lines.append(f"\n- {key} ({param_type})")
                lines.append(f"  description: {param_desc}")
                lines.append(f"  default: {param_default}")
                lines.append(f"  required: {param_required}")
                if "enum" in info:
                    lines.append(f"  choices: {info['enum']}")
                constraints = []
                if "minimum" in info:
                    constraints.append(f"min={info['minimum']}")
                if "maximum" in info:
                    constraints.append(f"max={info['maximum']}")
                if constraints:
                    lines.append(f"  constraints: {', '.join(constraints)}")

        ports_def = module_info.get("ports_definition", {})
        if ports_def:
            lines.append("\nPorts:")
            inputs = ports_def.get("inputs", [])
            if inputs:
                lines.append("\nInput ports:")
                for port in inputs:
                    label = _port_label(port)
                    desc = port.get("description", "")
                    port_type = port.get("type", "any")
                    condition = port.get("condition", "always")
                    lines.append(f"- {label} ({port_type})")
                    lines.append(f"  {desc}")
                    if condition != "always":
                        lines.append(f"  condition: {condition}")
            outputs = ports_def.get("outputs", [])
            if outputs:
                lines.append("\nOutput ports:")
                for port in outputs:
                    label = _port_label(port)
                    desc = port.get("description", "")
                    port_type = port.get("type", "any")
                    condition = port.get("condition", "always")
                    lines.append(f"- {label} ({port_type})")
                    lines.append(f"  {desc}")
                    if condition != "always":
                        lines.append(f"  condition: {condition}")

        template = module_info.get("template_json", {})
        if template:
            lines.append("\nTemplate JSON:")
            lines.append("```json")
            lines.append(json.dumps(template, ensure_ascii=False, indent=2))
            lines.append("```")

    lines.append(f"\n{'=' * 80}")
    return "\n".join(lines)


def get_module_summary(retrieval_bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a structured summary from formal retrieval results."""
    relevant_nodes = get_bundle_atomic_modules(retrieval_bundle)
    metadata = retrieval_bundle.get("metadata", {}) if isinstance(retrieval_bundle, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    avg_similarity = metadata.get("avg_atomic_score", 0)

    return {
        "total_modules": len(relevant_nodes),
        "module_types": [node.get("module_type") for node in relevant_nodes],
        "top_module": relevant_nodes[0] if relevant_nodes else None,
        "avg_similarity": avg_similarity,
        "categories": sorted(
            {
                str(node.get("category", "")).split("/")[0]
                for node in relevant_nodes
                if node.get("category")
            }
        ),
    }
