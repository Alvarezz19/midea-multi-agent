"""Phase 3/4 contract types and empty payload factories."""
from __future__ import annotations

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
    from_node: str
    from_port: int
    to_node: str
    to_port: int
    signal_name: str


class SubsystemPlan(TypedDict, total=False):
    subsystem_id: str
    page_id: str
    implementation_mode: str
    template_binding: Dict[str, Any]
    template_interface_bindings: List[InterfaceBindingSpec]
    node_instances: List[SubsystemPlanNode]
    edges: List[SubsystemPlanEdge]
    imported_signals: List[SubsystemSignalBinding]
    exported_signals: List[SubsystemSignalBinding]
    constraints: List[Dict[str, Any]]
    unresolved_items: List[Dict[str, Any]]
    reasoning: str


DEFAULT_RETRY_BUDGET: Dict[str, int] = {
    "planning": 2,
    "assembly": 2,
    "compile": 2,
}
VALID_REPAIR_SCOPES = tuple(DEFAULT_RETRY_BUDGET.keys())
VALID_ROUTE_DECISIONS = (
    "accept",
    "planning_repair",
    "assembly_repair",
    "compile_repair",
    "reject",
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


class RepairHistoryEntry(TypedDict, total=False):
    round: int
    scope: str
    issue_ids: List[str]
    target_state_keys: List[str]
    actions: List[str]
    result: str
    next_node: str


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
        "template_interface_bindings": [],
        "node_instances": [],
        "edges": [],
        "imported_signals": [],
        "exported_signals": [],
        "constraints": [],
        "unresolved_items": [],
        "reasoning": "",
    }


def default_retry_budget() -> Dict[str, int]:
    return dict(DEFAULT_RETRY_BUDGET)


def default_retry_counts_by_scope() -> Dict[str, int]:
    return {scope: 0 for scope in VALID_REPAIR_SCOPES}
