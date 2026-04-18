"""Phase 3/4/8 contract types and empty payload factories."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, TypedDict


class RequirementSignals(TypedDict):
    inputs: List[str]
    outputs: List[str]
    software_points: List[str]
    alarm_points: List[str]


class RequirementSubsystem(TypedDict, total=False):
    subsystem_id: str
    subsystem_type: str
    goal: str
    page_hint: str
    priority: int
    preferred_templates: List[str]
    imports: List[str]
    exports: List[str]
    reasoning: str


class RequirementSpec(TypedDict, total=False):
    schema_version: str
    system_type: str
    scenario_summary: str
    subsystems: List[RequirementSubsystem]
    signals: RequirementSignals
    required_pages: List[str]
    global_modes: List[str]
    ambiguities: List[str]
    assumptions: List[str]
    acceptance_criteria: List[str]
    confidence: float
    warnings: List[str]


class DecompositionPage(TypedDict, total=False):
    page_id: str
    label: str
    kind: str
    order: int
    source: str


class SubsystemDescriptor(TypedDict, total=False):
    subsystem_id: str
    subsystem_type: str
    page_id: str
    goal: str
    implementation_preference: str
    interface_bindings: List["InterfaceBindingSpec"]
    imports: List[str]
    exports: List[str]
    priority: int
    reasoning: str


class DecompositionResult(TypedDict, total=False):
    pages: List[DecompositionPage]
    subsystem_descriptors: List[SubsystemDescriptor]
    shared_signal_registry: List[Dict[str, Any]]
    template_needs: List[Dict[str, Any]]
    planning_order: List[str]
    warnings: List[str]


class ArchitecturePage(TypedDict, total=False):
    page_id: str
    label: str
    kind: str
    order: int
    source: str


class SubsystemSlot(TypedDict, total=False):
    subsystem_id: str
    page_id: str
    preferred_implementation: str
    preferred_template_ids: List[str]
    score_breakdown: List[Dict[str, Any]]
    selection_reason: str
    degrade_reason: str
    fallback_mode: str
    priority: int
    reasoning: str


class ArchitecturePlan(TypedDict, total=False):
    goal: str
    pages: List[ArchitecturePage]
    subsystem_slots: List[SubsystemSlot]
    shared_signal_registry: List[Dict[str, Any]]
    global_constraints: List[Dict[str, Any]]
    naming_strategy: Dict[str, Any]
    layout_strategy: Dict[str, Any]
    pattern_bindings: List[Dict[str, Any]]
    warnings: List[str]


class InterfaceBindingSpec(TypedDict, total=False):
    signal_name: str
    signal_key: str
    canonical_signal_key: str
    direction: str
    binding_kind: str
    allowed_external: bool
    owner_subsystem_id: str
    port_index: int
    evidence: List[str]
    confidence: float


class SharedSignalRegistryEntry(TypedDict, total=False):
    signal_name: str
    signal_key: str
    canonical_signal_key: str
    semantic_role: str
    owner_subsystem_id: str
    allowed_external: bool
    required_exporter_count: int
    consumers: List[str]
    exporter_candidates: List[str]
    candidate_exporters: List[str]
    resolution_status: str
    resolution_evidence: List[str]
    source_reason: str


class SubsystemSignalBinding(TypedDict, total=False):
    signal_name: str
    signal_key: str
    canonical_signal_key: str
    node_logic_id: str
    port_index: int
    page_id: str
    binding_kind: str
    allowed_external: bool
    owner_subsystem_id: str
    candidate_exporters: List[str]
    resolution_status: str
    resolution_evidence: List[str]
    semantic_role: str
    required: bool
    reasoning: str


class SubsystemPlanNode(TypedDict, total=False):
    logic_id: str
    module_type: str
    page_id: str
    template_id: str | None
    parameters: Dict[str, Any]
    input_count: int
    output_count: int
    position: Dict[str, int]
    reasoning: str


class SubsystemPlanEdge(TypedDict, total=False):
    edge_id: str
    from_node: str
    from_port: int
    to_node: str
    to_port: int
    signal_name: str


class SubsystemPlan(TypedDict, total=False):
    subsystem_id: str
    page_id: str
    dispatch_index: int
    implementation_mode: str
    template_binding: Dict[str, Any]
    selection_reason: str
    degrade_reason: str
    template_interface_bindings: List[InterfaceBindingSpec]
    node_instances: List[SubsystemPlanNode]
    edges: List[SubsystemPlanEdge]
    imported_signals: List[SubsystemSignalBinding]
    exported_signals: List[SubsystemSignalBinding]
    constraints: List[Dict[str, Any]]
    unresolved_items: List[Dict[str, Any]]
    reasoning: str


class ParallelMergeConflict(TypedDict, total=False):
    type: str
    subsystem_id: str
    conflicting_subsystem_ids: List[str]
    dispatch_index: int
    signal_name: str
    resolution: str
    message: str


class SubsystemPlanningDispatch(TypedDict, total=False):
    subsystem_id: str
    dispatch_index: int
    page_id: str
    subsystem_type: str
    worker_mode: str
    signal_name: str


DEFAULT_RETRY_BUDGET: Dict[str, int] = {
    "planning": 2,
    "assembly": 2,
    "compile": 2,
}
VALID_REPAIR_SCOPES = tuple(DEFAULT_RETRY_BUDGET.keys())
VALID_HITL_STAGES = (
    "none",
    "clarification_review",
    "architecture_review",
    "repair_review",
)
VALID_REVIEW_DECISIONS = (
    "approve",
    "feedback",
    "reject",
    "clarify",
)
VALID_REVIEW_STATUS = (
    "none",
    "not_required",
    "pending",
    "interrupted",
    "assumed",
    "answered",
    "applied",
    "rejected",
)
VALID_ROUTE_DECISIONS = (
    "accept",
    "planning_repair",
    "assembly_repair",
    "compile_repair",
    "reject",
)
CLARIFICATION_ALLOWED_REQUIREMENT_KEYS = (
    "system_type",
    "scenario_summary",
    "subsystems",
    "signals",
    "required_pages",
    "global_modes",
    "ambiguities",
    "assumptions",
    "acceptance_criteria",
    "warnings",
    "confidence",
)
ARCHITECTURE_FEEDBACK_ALLOWED_REQUIREMENT_KEYS = (
    "system_type",
    "scenario_summary",
    "subsystems",
    "signals",
    "required_pages",
    "global_modes",
    "ambiguities",
    "assumptions",
    "acceptance_criteria",
    "warnings",
    "confidence",
)
REVIEW_BLOCKED_STATE_KEYS = (
    "retrieval_bundle",
    "decomposition_result",
    "architecture_plan",
    "subsystem_plan_map",
    "assembled_graph_ir",
    "compiled_artifact",
    "verification_report",
    "final_output",
)


class RepairContext(TypedDict, total=False):
    repair_round: int
    repair_scope: str
    issue_ids: List[str]
    target_ids: List[str]
    target_state_keys: List[str]
    repair_strategy: str
    patch_instructions: List[str]
    resume_node: str


class RepairPatchPlan(TypedDict, total=False):
    repair_round: int
    repair_scope: str
    issue_ids: List[str]
    target_ids: List[str]
    target_state_keys: List[str]
    repair_strategy: str
    patch_instructions: List[str]
    resume_node: str
    decision: str
    reason: str
    result: str
    retry_budget: Dict[str, int]
    retry_counts_by_scope: Dict[str, int]
    operations: List[Dict[str, Any]]


class RepairHistoryEntry(TypedDict, total=False):
    round: int
    scope: str
    issue_ids: List[str]
    target_state_keys: List[str]
    actions: List[str]
    result: str
    next_node: str


class ReviewRequest(TypedDict, total=False):
    review_id: str
    stage: str
    question: str
    options: List[Dict[str, Any]]
    context_summary: str
    created_at: str


class ReviewResponse(TypedDict, total=False):
    decision: str
    answers: List[Any]
    feedback: str
    updated_constraints: Dict[str, Any]
    review_id: str


class ReviewHistoryEntry(TypedDict, total=False):
    review_id: str
    stage: str
    status: str
    request: ReviewRequest
    response: ReviewResponse
    created_at: str
    updated_at: str


class RouteDecision(TypedDict, total=False):
    decision: str
    repair_scope: str
    next_node: str
    reason: str
    issue_ids: List[str]
    retry_exhausted: bool
    retry_count_for_scope: int
    retry_budget_for_scope: int


def empty_requirement_spec() -> RequirementSpec:
    return {
        "schema_version": "3.0",
        "system_type": "",
        "scenario_summary": "",
        "subsystems": [],
        "signals": {
            "inputs": [],
            "outputs": [],
            "software_points": [],
            "alarm_points": [],
        },
        "required_pages": [],
        "global_modes": [],
        "ambiguities": [],
        "assumptions": [],
        "acceptance_criteria": [],
        "confidence": 0.0,
        "warnings": [],
    }


def empty_review_request() -> ReviewRequest:
    return {
        "review_id": "",
        "stage": "none",
        "question": "",
        "options": [],
        "context_summary": "",
        "created_at": "",
    }


def empty_review_response() -> ReviewResponse:
    return {
        "decision": "",
        "answers": [],
        "feedback": "",
        "updated_constraints": {},
        "review_id": "",
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_review_id(stage: str, review_history: list[dict[str, Any]] | None = None) -> str:
    stage_name = str(stage or "").strip()
    prefix_map = {
        "clarification_review": "clarification",
        "architecture_review": "architecture",
        "repair_review": "repair",
    }
    prefix = prefix_map.get(stage_name, stage_name or "review")
    existing_count = sum(
        1
        for entry in (review_history or [])
        if str((entry or {}).get("stage", "")).strip() == stage_name
    )
    return f"{prefix}-{existing_count + 1:03d}"


def upsert_review_history_entry(
    history: list[dict[str, Any]] | None,
    *,
    stage: str,
    review_id: str,
    status: str,
    request: dict[str, Any],
    response: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timestamp = utc_now_iso()
    next_history = [dict(entry or {}) for entry in (history or [])]
    for entry in next_history:
        if str(entry.get("review_id", "")).strip() != review_id:
            continue
        entry["stage"] = stage
        entry["status"] = status
        entry["request"] = dict(request or {})
        if response is not None:
            entry["response"] = dict(response or {})
        entry["updated_at"] = timestamp
        return next_history

    next_history.append(
        {
            "review_id": review_id,
            "stage": stage,
            "status": status,
            "request": dict(request or {}),
            "response": dict(response or empty_review_response()),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    return next_history


def empty_decomposition_result() -> DecompositionResult:
    return {
        "pages": [],
        "subsystem_descriptors": [],
        "shared_signal_registry": [],
        "template_needs": [],
        "planning_order": [],
        "warnings": [],
    }


def empty_architecture_plan() -> ArchitecturePlan:
    return {
        "goal": "",
        "pages": [],
        "subsystem_slots": [],
        "shared_signal_registry": [],
        "global_constraints": [],
        "naming_strategy": {},
        "layout_strategy": {},
        "pattern_bindings": [],
        "warnings": [],
    }


def empty_subsystem_plan(subsystem_id: str = "", page_id: str = "") -> SubsystemPlan:
    return {
        "subsystem_id": subsystem_id,
        "page_id": page_id,
        "implementation_mode": "",
        "template_binding": {},
        "selection_reason": "",
        "degrade_reason": "",
        "template_interface_bindings": [],
        "node_instances": [],
        "edges": [],
        "imported_signals": [],
        "exported_signals": [],
        "constraints": [],
        "unresolved_items": [],
        "reasoning": "",
    }


def empty_parallel_merge_conflicts() -> List[ParallelMergeConflict]:
    return []


def _normalize_subsystem_id(value: Any) -> str:
    return str(value or "").strip()


def _coerce_dispatch_index(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**9


def order_subsystem_plan_map(subsystem_plan_map: Dict[str, Any] | None) -> Dict[str, Any]:
    ordered_items = sorted(
        (subsystem_plan_map or {}).items(),
        key=lambda item: (
            _coerce_dispatch_index((item[1] or {}).get("dispatch_index")),
            _normalize_subsystem_id(item[0]),
        ),
    )
    return {
        _normalize_subsystem_id(subsystem_id): dict(plan or {})
        for subsystem_id, plan in ordered_items
    }


def merge_subsystem_plan_map(
    current: Dict[str, Any] | None,
    update: Dict[str, Any] | None,
) -> Dict[str, Any]:
    merged = {
        _normalize_subsystem_id(subsystem_id): dict(plan or {})
        for subsystem_id, plan in (current or {}).items()
        if _normalize_subsystem_id(subsystem_id)
    }

    for raw_subsystem_id, raw_plan in (update or {}).items():
        subsystem_id = _normalize_subsystem_id(raw_subsystem_id)
        if not subsystem_id:
            raise ValueError("blank_subsystem_id")

        plan = dict(raw_plan or {})
        plan_subsystem_id = _normalize_subsystem_id(plan.get("subsystem_id") or subsystem_id)
        if plan_subsystem_id != subsystem_id:
            raise ValueError(f"subsystem_id_mismatch:{subsystem_id}:{plan_subsystem_id}")

        if subsystem_id in merged:
            raise ValueError(f"duplicate_subsystem_id:{subsystem_id}")

        plan["subsystem_id"] = subsystem_id
        merged[subsystem_id] = plan

    return order_subsystem_plan_map(merged)


def merge_parallel_conflicts(
    current: List[ParallelMergeConflict] | None,
    update: List[ParallelMergeConflict] | None,
) -> List[ParallelMergeConflict]:
    return list(current or []) + list(update or [])


def default_retry_budget() -> Dict[str, int]:
    return dict(DEFAULT_RETRY_BUDGET)


def default_retry_counts_by_scope() -> Dict[str, int]:
    return {scope: 0 for scope in VALID_REPAIR_SCOPES}


def normalize_review_response(payload: Any, *, review_id: str = "") -> ReviewResponse:
    if not isinstance(payload, dict):
        raise ValueError("resume payload 必须是 dict。")

    decision = str(payload.get("decision", "")).strip()
    if decision not in VALID_REVIEW_DECISIONS:
        raise ValueError(f"unsupported_review_decision:{decision or '<empty>'}")

    answers = payload.get("answers", [])
    if not isinstance(answers, list):
        raise ValueError("resume payload.answers 必须是 list。")

    feedback = str(payload.get("feedback", "") or "").strip()
    updated_constraints = payload.get("updated_constraints", {})
    if not isinstance(updated_constraints, dict):
        raise ValueError("resume payload.updated_constraints 必须是 dict。")

    normalized_review_id = str(payload.get("review_id", "") or "").strip() or str(review_id or "").strip()
    if review_id and normalized_review_id != review_id:
        raise ValueError(f"review_id_mismatch:{review_id}:{normalized_review_id or '<empty>'}")

    return {
        "decision": decision,
        "answers": list(answers),
        "feedback": feedback,
        "updated_constraints": dict(updated_constraints),
        "review_id": normalized_review_id,
    }


def merge_requirement_side_patch(
    requirement_spec: Dict[str, Any] | None,
    patch: Dict[str, Any] | None,
    *,
    allowed_keys: tuple[str, ...],
) -> Dict[str, Any]:
    merged = dict(requirement_spec or {})
    patch_dict = dict(patch or {})

    for blocked_key in REVIEW_BLOCKED_STATE_KEYS:
        if blocked_key in patch_dict:
            raise ValueError(f"review_patch_forbidden:{blocked_key}")

    for key, value in patch_dict.items():
        if key not in allowed_keys:
            raise ValueError(f"review_patch_unsupported:{key}")
        merged[key] = value

    return merged
