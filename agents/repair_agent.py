"""Deterministic repair agent for the Phase 4 repair loop."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from utils.phase3_contracts import default_retry_budget, default_retry_counts_by_scope
from utils.signal_semantics import canonicalize_signal_name


SUPPORTED_RULE_IDS_BY_SCOPE = {
    "planning": {
        "ir.unresolved.ambiguous_shared_signal",
        "ir.unresolved.synthetic_shared_signal_source",
        "ir.unresolved.shared_signal_owner_mismatch",
    },
    "assembly": {
        "ir.unresolved.missing_local_edge_endpoint",
    },
    "compile": {
        "compile.wire.port.range",
    },
}
IGNORABLE_RULE_IDS_BY_SCOPE = {
    "planning": {"plan.unresolved_items.must_be_resolved"},
    "assembly": set(),
    "compile": set(),
}
RESUME_NODE_BY_SCOPE = {
    "planning": "subsystem_planning",
    "assembly": "global_assembly",
    "compile": "coding",
}
TARGET_STATE_KEYS_BY_SCOPE = {
    "planning": ["architecture_plan", "decomposition_result"],
    "assembly": ["subsystem_plan_map"],
    "compile": ["assembled_graph_ir"],
}
INVALIDATE_STATE_BY_SCOPE = {
    "planning": ["subsystem_plan_map", "assembled_graph_ir", "compiled_artifact", "verification_report", "final_output", "execution_plan", "generated_code"],
    "assembly": ["assembled_graph_ir", "compiled_artifact", "verification_report", "final_output", "execution_plan", "generated_code"],
    "compile": ["compiled_artifact", "verification_report", "final_output", "generated_code"],
}
REPAIR_STRATEGY_BY_SCOPE = {
    "planning": "rebind_shared_signal_owner",
    "assembly": "remove_invalid_local_edges",
    "compile": "repair_compile_wires",
}


class RepairIssueReject(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _normalize_retry_budget(retry_budget: Dict[str, Any] | None) -> Dict[str, int]:
    normalized = default_retry_budget()
    for scope, default_value in normalized.items():
        if retry_budget is None:
            normalized[scope] = default_value
            continue
        normalized[scope] = _coerce_non_negative_int(retry_budget.get(scope), default_value)
    return normalized


def _normalize_retry_counts_by_scope(retry_counts_by_scope: Dict[str, Any] | None) -> Dict[str, int]:
    normalized = default_retry_counts_by_scope()
    for scope in normalized:
        if retry_counts_by_scope is None:
            normalized[scope] = 0
            continue
        normalized[scope] = _coerce_non_negative_int(retry_counts_by_scope.get(scope), 0)
    return normalized


def _collect_external_signal_keys(requirement_spec: Dict[str, Any]) -> set[str]:
    signals = requirement_spec.get("signals", {}) if isinstance(requirement_spec.get("signals"), dict) else {}
    values: List[Any] = []
    for key in ("inputs", "software_points"):
        values.extend(list(signals.get(key, []) or []))
    values.extend(list(requirement_spec.get("global_modes", []) or []))
    return {
        normalized
        for value in values
        if (normalized := canonicalize_signal_name(value))
    }


def _normalize_string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _iter_shared_signal_registries(state: Dict[str, Any]) -> Iterable[tuple[str, List[Dict[str, Any]]]]:
    architecture_plan = state.get("architecture_plan", {}) or {}
    decomposition_result = state.get("decomposition_result", {}) or {}
    if not isinstance(architecture_plan.get("shared_signal_registry"), list):
        architecture_plan["shared_signal_registry"] = []
    if not isinstance(decomposition_result.get("shared_signal_registry"), list):
        decomposition_result["shared_signal_registry"] = []
    yield "architecture_plan", architecture_plan["shared_signal_registry"]
    yield "decomposition_result", decomposition_result["shared_signal_registry"]


def _upsert_shared_signal_entry(registry: List[Dict[str, Any]], signal_name: str) -> Dict[str, Any]:
    signal_key = canonicalize_signal_name(signal_name)
    for entry in registry:
        if canonicalize_signal_name(entry.get("canonical_signal_key") or entry.get("signal_key") or entry.get("signal_name")) == signal_key:
            if not entry.get("signal_name"):
                entry["signal_name"] = signal_name
            if not entry.get("signal_key"):
                entry["signal_key"] = signal_key
            entry.setdefault("canonical_signal_key", signal_key)
            return entry
    entry = {
        "signal_name": signal_name,
        "signal_key": signal_key,
        "canonical_signal_key": signal_key,
        "owner_subsystem_id": "",
        "allowed_external": False,
        "required_exporter_count": 1,
        "candidate_exporters": [],
        "resolution_status": "unresolved",
        "resolution_evidence": [],
        "consumers": [],
        "source_reason": "Inserted by RepairAgent.",
    }
    registry.append(entry)
    return entry


def _append_resolution_evidence(entry: Dict[str, Any], evidence: str) -> None:
    evidence = str(evidence or "").strip()
    if not evidence:
        return
    evidence_list = entry.get("resolution_evidence")
    if not isinstance(evidence_list, list):
        evidence_list = []
    if evidence not in evidence_list:
        evidence_list.append(evidence)
    entry["resolution_evidence"] = evidence_list


def _collect_descriptor_exporters(decomposition_result: Dict[str, Any], signal_key: str) -> List[str]:
    exporters: List[str] = []
    for descriptor in decomposition_result.get("subsystem_descriptors", []) or []:
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        if not subsystem_id:
            continue
        for binding in descriptor.get("interface_bindings", []) or []:
            if not isinstance(binding, dict):
                continue
            if str(binding.get("direction", "")).strip() != "output":
                continue
            binding_key = canonicalize_signal_name(
                binding.get("canonical_signal_key")
                or binding.get("signal_key")
                or binding.get("signal_name")
            )
            if binding_key == signal_key and subsystem_id not in exporters:
                exporters.append(subsystem_id)
        for signal_name in descriptor.get("exports", []) or []:
            if canonicalize_signal_name(signal_name) == signal_key and subsystem_id not in exporters:
                exporters.append(subsystem_id)
    return exporters


def _collect_plan_exporters(subsystem_plan_map: Dict[str, Dict[str, Any]], signal_key: str) -> List[str]:
    exporters: List[str] = []
    for subsystem_id, subsystem_plan in (subsystem_plan_map or {}).items():
        for binding in subsystem_plan.get("exported_signals", []) or []:
            binding_key = canonicalize_signal_name(
                binding.get("canonical_signal_key")
                or binding.get("signal_key")
                or binding.get("signal_name")
            )
            if binding_key == signal_key and subsystem_id not in exporters:
                exporters.append(subsystem_id)
    return exporters


def _collect_current_owner_candidates(state: Dict[str, Any], signal_key: str) -> List[str]:
    candidates: List[str] = []
    for _, registry in _iter_shared_signal_registries(state):
        for entry in registry:
            if canonicalize_signal_name(entry.get("canonical_signal_key") or entry.get("signal_key") or entry.get("signal_name")) != signal_key:
                continue
            owner_subsystem_id = str(entry.get("owner_subsystem_id", "")).strip()
            if owner_subsystem_id and owner_subsystem_id not in candidates:
                candidates.append(owner_subsystem_id)
    return candidates


def _collect_candidate_exporters_from_state(state: Dict[str, Any], signal_key: str) -> List[str]:
    descriptor_exporters = _collect_descriptor_exporters(state.get("decomposition_result", {}) or {}, signal_key)
    plan_exporters = _collect_plan_exporters(state.get("subsystem_plan_map", {}) or {}, signal_key)
    current_owners = _collect_current_owner_candidates(state, signal_key)

    merged_candidates: List[str] = []
    for candidate_list in (plan_exporters, descriptor_exporters, current_owners):
        for candidate in candidate_list:
            if candidate and candidate not in merged_candidates:
                merged_candidates.append(candidate)
    return merged_candidates


def _resolve_unique_candidate_exporter(
    state: Dict[str, Any],
    signal_key: str,
    candidate_exporters: List[str] | None = None,
    *,
    strict_candidates: bool = False,
) -> tuple[str, List[str], List[str]]:
    preferred_candidates = _normalize_string_list(candidate_exporters)
    actual_candidates = _collect_candidate_exporters_from_state(state, signal_key)

    filtered_candidates = list(preferred_candidates)
    if preferred_candidates and actual_candidates:
        overlapping_candidates = [candidate for candidate in preferred_candidates if candidate in actual_candidates]
        if overlapping_candidates:
            filtered_candidates = overlapping_candidates
    elif not preferred_candidates:
        filtered_candidates = list(actual_candidates)

    if len(filtered_candidates) == 1:
        return filtered_candidates[0], filtered_candidates, actual_candidates
    if not strict_candidates and len(actual_candidates) == 1:
        return actual_candidates[0], actual_candidates, actual_candidates
    return "", filtered_candidates, actual_candidates


def _upsert_shared_signal_constraint(architecture_plan: Dict[str, Any], signal_name: str, owner_subsystem_id: str) -> None:
    constraints = architecture_plan.get("global_constraints", []) or []
    signal_key = canonicalize_signal_name(signal_name)
    constraint_ids = {f"shared_signal_owner::{signal_key}", f"shared_signal::{signal_key}"}
    for constraint in constraints:
        if str(constraint.get("constraint_id", "")).strip() in constraint_ids:
            constraint["value"] = owner_subsystem_id
            constraint["source"] = "repair_agent"
            architecture_plan["global_constraints"] = constraints
            return
    constraints.append(
        {
            "constraint_id": f"shared_signal_owner::{signal_key}",
            "value": owner_subsystem_id,
            "source": "repair_agent",
        }
    )
    architecture_plan["global_constraints"] = constraints


def _reclassify_signal_bindings_as_external(
    decomposition_result: Dict[str, Any],
    signal_name: str,
    canonical_signal_key: str,
    binding_kind: str,
) -> List[str]:
    patched_subsystems: List[str] = []
    for descriptor in decomposition_result.get("subsystem_descriptors", []) or []:
        if not isinstance(descriptor, dict):
            continue
        subsystem_id = str(descriptor.get("subsystem_id", "")).strip()
        patched_here = False
        bindings = descriptor.get("interface_bindings", [])
        if isinstance(bindings, list):
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                binding_key = canonicalize_signal_name(
                    binding.get("canonical_signal_key")
                    or binding.get("signal_key")
                    or binding.get("signal_name")
                )
                if str(binding.get("direction", "")).strip() != "input" or binding_key != canonical_signal_key:
                    continue
                binding["binding_kind"] = binding_kind
                binding["allowed_external"] = True
                binding["owner_subsystem_id"] = ""
                binding["canonical_signal_key"] = canonical_signal_key
                binding.setdefault("evidence", []).append("Reclassified as external by RepairAgent.")
                patched_here = True
        if patched_here:
            if subsystem_id and subsystem_id not in patched_subsystems:
                patched_subsystems.append(subsystem_id)
            continue
        for signal_list_key in ("imports",):
            for item in descriptor.get(signal_list_key, []) or []:
                if canonicalize_signal_name(item) == canonical_signal_key and subsystem_id and subsystem_id not in patched_subsystems:
                    patched_subsystems.append(subsystem_id)
    return patched_subsystems


def _build_instance_lookup(assembled_graph_ir: Dict[str, Any], id_map: Dict[str, str]) -> Dict[str, str]:
    node_instance_ids = {
        str(node.get("instance_id", "")).strip()
        for node in assembled_graph_ir.get("node_instances", []) or []
        if str(node.get("instance_id", "")).strip()
    }
    lookup: Dict[str, str] = {}
    for graph_key, real_id in (id_map or {}).items():
        graph_key = str(graph_key).strip()
        real_id = str(real_id).strip()
        if graph_key in node_instance_ids and real_id and real_id not in lookup:
            lookup[real_id] = graph_key
    return lookup


class RepairAgent:
    """Apply deterministic upstream repairs before rerunning downstream nodes."""

    def _select_scope_issues(self, state: Dict[str, Any], repair_scope: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        verification_report = state.get("verification_report", {}) or {}
        route_decision = state.get("route_decision", {}) or {}
        allowed_issue_ids = set(route_decision.get("issue_ids", []) or [])
        selected_issues = []
        for issue in verification_report.get("issues", []) or []:
            issue_id = str((issue or {}).get("issue_id", "")).strip()
            issue_scope = str((issue or {}).get("scope", "")).strip()
            if issue_scope != repair_scope:
                continue
            if allowed_issue_ids and issue_id not in allowed_issue_ids:
                continue
            selected_issues.append(issue)

        supported_rule_ids = SUPPORTED_RULE_IDS_BY_SCOPE.get(repair_scope, set())
        ignorable_rule_ids = IGNORABLE_RULE_IDS_BY_SCOPE.get(repair_scope, set())
        repairable = [issue for issue in selected_issues if str(issue.get("rule_id", "")).strip() in supported_rule_ids]
        unsupported = [
            issue
            for issue in selected_issues
            if str(issue.get("rule_id", "")).strip() not in supported_rule_ids | ignorable_rule_ids
        ]
        return repairable, unsupported

    def _reject(
        self,
        state: Dict[str, Any],
        *,
        repair_scope: str,
        issue_ids: List[str],
        repair_round: int,
        retry_budget: Dict[str, int],
        retry_counts_by_scope: Dict[str, int],
        reason: str,
        actions: List[str],
    ) -> Dict[str, Any]:
        state["repair_context"] = {
            "repair_round": repair_round,
            "repair_scope": repair_scope,
            "issue_ids": issue_ids,
            "target_ids": [],
            "target_state_keys": TARGET_STATE_KEYS_BY_SCOPE.get(repair_scope, []),
            "repair_strategy": "reject",
            "patch_instructions": actions,
            "resume_node": "",
        }
        state.setdefault("repair_history", []).append(
            {
                "round": repair_round,
                "scope": repair_scope,
                "issue_ids": issue_ids,
                "target_state_keys": TARGET_STATE_KEYS_BY_SCOPE.get(repair_scope, []),
                "actions": actions,
                "result": "rejected",
                "next_node": "END",
            }
        )
        state["route_decision"] = {
            "decision": "reject",
            "repair_scope": repair_scope,
            "next_node": "END",
            "reason": reason,
            "issue_ids": issue_ids,
            "retry_exhausted": False,
            "retry_count_for_scope": retry_counts_by_scope.get(repair_scope, 0),
            "retry_budget_for_scope": retry_budget.get(repair_scope, 0),
        }
        state["current_step"] = "repair_rejected"
        return state

    def _invalidate_downstream(self, state: Dict[str, Any], repair_scope: str) -> None:
        for key in INVALIDATE_STATE_BY_SCOPE.get(repair_scope, []):
            if key == "generated_code":
                state[key] = ""
            else:
                state[key] = {}

    def _mark_shared_signal_as_external(
        self,
        state: Dict[str, Any],
        architecture_plan: Dict[str, Any],
        decomposition_result: Dict[str, Any],
        *,
        signal_name: str,
        signal_key: str,
        binding_kind: str,
    ) -> str:
        for _, registry in _iter_shared_signal_registries(state):
            entry = _upsert_shared_signal_entry(registry, signal_name)
            entry["owner_subsystem_id"] = ""
            entry["allowed_external"] = True
            entry["required_exporter_count"] = 0
            entry["candidate_exporters"] = []
            entry["resolution_status"] = "resolved_external_input"
            entry["source_reason"] = "Marked as an allowed external signal by RepairAgent."
            _append_resolution_evidence(entry, "RepairAgent reclassified the signal as an allowed external input.")
        _upsert_shared_signal_constraint(architecture_plan, signal_name, "")
        patched_subsystems = _reclassify_signal_bindings_as_external(
            decomposition_result,
            signal_name,
            signal_key,
            binding_kind,
        )
        action = f"将共享信号 {signal_name} 重分类为 {binding_kind}。"
        if patched_subsystems:
            action += f" 影响子系统: {', '.join(sorted(patched_subsystems))}。"
        return action

    def _bind_shared_signal_owner(
        self,
        state: Dict[str, Any],
        architecture_plan: Dict[str, Any],
        *,
        signal_name: str,
        owner_subsystem_id: str,
        candidate_exporters: List[str],
        resolution_status: str,
        resolution_evidence: str,
    ) -> str:
        normalized_candidates = _normalize_string_list(candidate_exporters) or [owner_subsystem_id]
        for _, registry in _iter_shared_signal_registries(state):
            entry = _upsert_shared_signal_entry(registry, signal_name)
            entry["owner_subsystem_id"] = owner_subsystem_id
            entry["allowed_external"] = False
            entry["required_exporter_count"] = 1
            entry["candidate_exporters"] = normalized_candidates
            entry["resolution_status"] = resolution_status
            entry["source_reason"] = "Rebound to a unique exporter by RepairAgent."
            _append_resolution_evidence(entry, resolution_evidence)
        _upsert_shared_signal_constraint(architecture_plan, signal_name, owner_subsystem_id)
        return f"将共享信号 {signal_name} 的 owner_subsystem_id 收敛为 {owner_subsystem_id}。"

    def _apply_planning_repair(self, state: Dict[str, Any], issues: List[Dict[str, Any]]) -> tuple[List[str], List[str]]:
        requirement_spec = state.get("requirement_spec", {}) or {}
        architecture_plan = state.get("architecture_plan", {}) or {}
        decomposition_result = state.get("decomposition_result", {}) or {}
        external_signal_keys = _collect_external_signal_keys(requirement_spec)

        actions: List[str] = []
        target_ids: List[str] = []

        for issue in issues:
            rule_id = str(issue.get("rule_id", "")).strip()
            repair_payload = issue.get("repair_payload", {}) if isinstance(issue.get("repair_payload"), dict) else {}
            signal_name = str(repair_payload.get("signal_name") or issue.get("target_id", "")).strip()
            signal_key = str(repair_payload.get("canonical_signal_key") or canonicalize_signal_name(signal_name)).strip()
            if not signal_key:
                raise ValueError("Planning repair issue is missing a signal target.")

            suggested_binding_kind = str(repair_payload.get("binding_kind", "")).strip() or "external_input"
            allowed_external = bool(repair_payload.get("allowed_external", False)) or signal_key in external_signal_keys
            candidate_exporters = _normalize_string_list(repair_payload.get("candidate_exporters"))
            resolution_status = str(repair_payload.get("resolution_status", "")).strip()
            is_ambiguous_issue = (
                rule_id == "ir.unresolved.ambiguous_shared_signal"
                or resolution_status == "ambiguous"
            )
            if is_ambiguous_issue:
                inferred_owner, filtered_candidates, actual_candidates = _resolve_unique_candidate_exporter(
                    state,
                    signal_key,
                    candidate_exporters,
                    strict_candidates=True,
                )
                if inferred_owner:
                    actions.append(
                        self._bind_shared_signal_owner(
                            state,
                            architecture_plan,
                            signal_name=signal_name,
                            owner_subsystem_id=inferred_owner,
                            candidate_exporters=filtered_candidates,
                            resolution_status="resolved_unique_exporter",
                            resolution_evidence="RepairAgent narrowed ambiguous candidate exporters to a single owner.",
                        )
                    )
                    target_ids.append(signal_name)
                    continue

                raw_candidates = candidate_exporters or actual_candidates
                filtered_text = ", ".join(filtered_candidates) if filtered_candidates else "none"
                raw_text = ", ".join(raw_candidates) if raw_candidates else "none"
                raise RepairIssueReject(
                    "ambiguous_shared_signal_unresolved",
                    f"共享信号 {signal_name} 无法收敛唯一 exporter。原始候选: {raw_text}; 过滤后: {filtered_text}。",
                )

            if allowed_external and suggested_binding_kind != "shared_signal":
                actions.append(
                    self._mark_shared_signal_as_external(
                        state,
                        architecture_plan,
                        decomposition_result,
                        signal_name=signal_name,
                        signal_key=signal_key,
                        binding_kind=suggested_binding_kind,
                    )
                )
                target_ids.append(signal_name)
                continue

            inferred_owner, filtered_candidates, actual_candidates = _resolve_unique_candidate_exporter(
                state,
                signal_key,
                candidate_exporters,
                strict_candidates=False,
            )
            if inferred_owner:
                actions.append(
                    self._bind_shared_signal_owner(
                        state,
                        architecture_plan,
                        signal_name=signal_name,
                        owner_subsystem_id=inferred_owner,
                        candidate_exporters=filtered_candidates or actual_candidates,
                        resolution_status="resolved_unique_exporter",
                        resolution_evidence="RepairAgent rebound the signal to a unique exporter.",
                    )
                )
                target_ids.append(signal_name)
                continue

            if allowed_external:
                actions.append(
                    self._mark_shared_signal_as_external(
                        state,
                        architecture_plan,
                        decomposition_result,
                        signal_name=signal_name,
                        signal_key=signal_key,
                        binding_kind=suggested_binding_kind,
                    )
                )
                target_ids.append(signal_name)
                continue

            raise ValueError(f"Unsupported planning repair target: {signal_name}")

        return actions, target_ids

    def _apply_assembly_repair(self, state: Dict[str, Any], issues: List[Dict[str, Any]]) -> tuple[List[str], List[str]]:
        subsystem_plan_map = state.get("subsystem_plan_map", {}) or {}
        actions: List[str] = []
        target_ids: List[str] = []

        for issue in issues:
            repair_payload = issue.get("repair_payload", {}) if isinstance(issue.get("repair_payload"), dict) else {}
            subsystem_id = str(repair_payload.get("subsystem_id") or issue.get("target_id", "")).strip()
            subsystem_plan = subsystem_plan_map.get(subsystem_id, {}) or {}
            old_edges = list(subsystem_plan.get("edges", []) or [])
            edge_ids = set(_normalize_string_list(repair_payload.get("edge_ids")))
            from_node = str(repair_payload.get("from_node", "")).strip()
            to_node = str(repair_payload.get("to_node", "")).strip()
            reason = str(repair_payload.get("reason") or issue.get("message") or "").strip()

            matching_edges: List[Dict[str, Any]] = []
            if edge_ids:
                matching_edges.extend(
                    edge
                    for edge in old_edges
                    if str(edge.get("edge_id", "")).strip() in edge_ids and edge not in matching_edges
                )
            if (from_node or to_node) and not matching_edges:
                matching_edges.extend(
                    edge
                    for edge in old_edges
                    if (not from_node or str(edge.get("from_node", "")).strip() == from_node)
                    and (not to_node or str(edge.get("to_node", "")).strip() == to_node)
                    and edge not in matching_edges
                )
            if not matching_edges:
                node_ids = {
                    str(node.get("logic_id", "")).strip()
                    for node in subsystem_plan.get("node_instances", []) or []
                    if str(node.get("logic_id", "")).strip()
                }
                matching_edges.extend(
                    edge
                    for edge in old_edges
                    if str(edge.get("from_node", "")).strip() not in node_ids
                    or str(edge.get("to_node", "")).strip() not in node_ids
                )

            removed_count = len(matching_edges)
            if removed_count <= 0:
                raise ValueError(f"No removable invalid local edges found for subsystem {subsystem_id}.")

            subsystem_plan["edges"] = [edge for edge in old_edges if edge not in matching_edges]
            subsystem_plan.setdefault("unresolved_items", []).append(
                {
                    "type": "degraded_removed_invalid_local_edge",
                    "severity": "warning",
                    "scope": "assembly",
                    "subsystem_id": subsystem_id,
                    "message": f"RepairAgent removed {removed_count} invalid local edges from subsystem {subsystem_id}.",
                    "reason": reason or "missing_local_edge_endpoint",
                    "edge_ids": sorted(
                        {
                            str(edge.get("edge_id", "")).strip()
                            for edge in matching_edges
                            if str(edge.get("edge_id", "")).strip()
                        }
                    ),
                    "suggested_fix": "补齐真实局部语义后再恢复被删除的边。",
                }
            )
            actions.append(
                f"按结构化 payload 删除子系统 {subsystem_id} 中 {removed_count} 条非法局部边，并记录降级告警。"
            )
            target_ids.extend(
                edge_id
                for edge_id in sorted(edge_ids)
                if edge_id
            )
            if not edge_ids:
                target_ids.append(subsystem_id)

        return actions, target_ids

    def _apply_compile_repair(self, state: Dict[str, Any], issues: List[Dict[str, Any]]) -> tuple[List[str], List[str]]:
        assembled_graph_ir = state.get("assembled_graph_ir", {}) or {}
        compiled_artifact = state.get("compiled_artifact", {}) or {}
        id_map = compiled_artifact.get("id_map", {}) or {}
        real_id_to_instance = _build_instance_lookup(assembled_graph_ir, id_map)
        node_map = {
            str(node.get("instance_id", "")).strip(): node
            for node in assembled_graph_ir.get("node_instances", []) or []
            if str(node.get("instance_id", "")).strip()
        }

        actions: List[str] = []
        target_ids: List[str] = []

        for issue in issues:
            repair_payload = issue.get("repair_payload", {}) if isinstance(issue.get("repair_payload"), dict) else {}
            source_real_id = str(repair_payload.get("source_real_id", "")).strip()
            source_instance = real_id_to_instance.get(source_real_id, "")
            target_real_id = str(repair_payload.get("target_real_id", "")).strip()
            invalid_target_port = repair_payload.get("invalid_target_port")
            target_input_count = repair_payload.get("target_input_count")
            if not source_real_id or not target_real_id or invalid_target_port is None:
                raise ValueError("Compile repair requires structured source/target/port fields in repair_payload.")

            invalid_target_port = int(invalid_target_port)
            target_instance = real_id_to_instance.get(target_real_id, "")
            if not source_instance or not target_instance:
                raise ValueError("Unable to map compiled ids back to assembled Graph IR instances.")

            target_node = node_map.get(target_instance, {})
            target_input_count = int(target_input_count or target_node.get("input_count", 0) or 0)
            if target_input_count <= 0:
                raise ValueError(f"Target node {target_instance} has no valid input ports to repair.")

            matching_edges = [
                edge
                for edge in assembled_graph_ir.get("edges", []) or []
                if str(edge.get("from_instance", "")).strip() == source_instance
                and str(edge.get("to_instance", "")).strip() == target_instance
                and int(edge.get("to_port", 0) or 0) == invalid_target_port
            ]
            if not matching_edges:
                raise ValueError("Unable to locate the offending assembled edge for compile repair.")

            clamped_port = min(invalid_target_port, target_input_count - 1)
            occupied_ports = {
                int(edge.get("to_port", 0) or 0)
                for edge in assembled_graph_ir.get("edges", []) or []
                if str(edge.get("to_instance", "")).strip() == target_instance and edge not in matching_edges
            }

            if clamped_port in occupied_ports:
                for edge in matching_edges:
                    assembled_graph_ir["edges"].remove(edge)
                actions.append(
                    f"删除指向 {target_instance}[{invalid_target_port}] 的非法编译边，避免端口夹断后发生冲突。"
                )
            else:
                for edge in matching_edges:
                    edge["to_port"] = clamped_port
                actions.append(
                    f"将指向 {target_instance} 的越界端口 {invalid_target_port} 夹断为 {clamped_port}。"
                )

            target_ids.append(target_instance)

        return actions, target_ids

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        route_decision = state.get("route_decision", {}) or {}
        verification_report = state.get("verification_report", {}) or {}
        repair_scope = str(route_decision.get("repair_scope") or verification_report.get("repair_scope") or "").strip()
        if repair_scope not in RESUME_NODE_BY_SCOPE:
            raise ValueError(f"Unsupported repair scope: {repair_scope or '<empty>'}")

        retry_budget = _normalize_retry_budget(state.get("retry_budget"))
        retry_counts_by_scope = _normalize_retry_counts_by_scope(state.get("retry_counts_by_scope"))
        retry_counts_by_scope[repair_scope] = retry_counts_by_scope.get(repair_scope, 0) + 1
        repair_round = retry_counts_by_scope[repair_scope]
        issue_ids = list(route_decision.get("issue_ids", []) or [])
        repairable_issues, unsupported_issues = self._select_scope_issues(state, repair_scope)

        state["retry_budget"] = retry_budget
        state["retry_counts_by_scope"] = retry_counts_by_scope
        state["retry_count"] = sum(retry_counts_by_scope.values())

        if unsupported_issues:
            unsupported_rule_ids = sorted({str(issue.get("rule_id", "")).strip() for issue in unsupported_issues})
            return self._reject(
                state,
                repair_scope=repair_scope,
                issue_ids=issue_ids,
                repair_round=repair_round,
                retry_budget=retry_budget,
                retry_counts_by_scope=retry_counts_by_scope,
                reason="unsupported_repair_issue",
                actions=[f"当前 repair scope 不支持自动修复规则: {', '.join(unsupported_rule_ids)}"],
            )

        if not repairable_issues:
            return self._reject(
                state,
                repair_scope=repair_scope,
                issue_ids=issue_ids,
                repair_round=repair_round,
                retry_budget=retry_budget,
                retry_counts_by_scope=retry_counts_by_scope,
                reason="no_repairable_issue",
                actions=["当前 repair scope 下没有可自动修复的 issue。"],
            )

        try:
            if repair_scope == "planning":
                actions, target_ids = self._apply_planning_repair(state, repairable_issues)
            elif repair_scope == "assembly":
                actions, target_ids = self._apply_assembly_repair(state, repairable_issues)
            elif repair_scope == "compile":
                actions, target_ids = self._apply_compile_repair(state, repairable_issues)
            else:
                raise ValueError(f"Unsupported repair scope: {repair_scope}")
        except RepairIssueReject as exc:
            return self._reject(
                state,
                repair_scope=repair_scope,
                issue_ids=issue_ids,
                repair_round=repair_round,
                retry_budget=retry_budget,
                retry_counts_by_scope=retry_counts_by_scope,
                reason=exc.reason,
                actions=[str(exc)],
            )
        except ValueError as exc:
            return self._reject(
                state,
                repair_scope=repair_scope,
                issue_ids=issue_ids,
                repair_round=repair_round,
                retry_budget=retry_budget,
                retry_counts_by_scope=retry_counts_by_scope,
                reason="repair_patch_failed",
                actions=[str(exc)],
            )

        resume_node = RESUME_NODE_BY_SCOPE[repair_scope]
        self._invalidate_downstream(state, repair_scope)

        state["repair_context"] = {
            "repair_round": repair_round,
            "repair_scope": repair_scope,
            "issue_ids": issue_ids,
            "target_ids": target_ids,
            "target_state_keys": TARGET_STATE_KEYS_BY_SCOPE[repair_scope],
            "repair_strategy": REPAIR_STRATEGY_BY_SCOPE[repair_scope],
            "patch_instructions": actions,
            "resume_node": resume_node,
        }
        state.setdefault("repair_history", []).append(
            {
                "round": repair_round,
                "scope": repair_scope,
                "issue_ids": issue_ids,
                "target_state_keys": TARGET_STATE_KEYS_BY_SCOPE[repair_scope],
                "actions": actions,
                "result": "patched",
                "next_node": resume_node,
            }
        )
        state["route_decision"] = {
            "decision": route_decision.get("decision", f"{repair_scope}_repair"),
            "repair_scope": repair_scope,
            "next_node": resume_node,
            "reason": "repair_patch_applied",
            "issue_ids": issue_ids,
            "retry_exhausted": False,
            "retry_count_for_scope": retry_counts_by_scope.get(repair_scope, 0),
            "retry_budget_for_scope": retry_budget.get(repair_scope, 0),
        }
        state["current_step"] = "repair_completed"
        return state
