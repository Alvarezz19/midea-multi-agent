"""Phase 3 contract types and empty payload factories."""
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
    global_constraints: List[Dict[str, Any]]
    naming_strategy: Dict[str, Any]
    layout_strategy: Dict[str, Any]
    pattern_bindings: List[Dict[str, Any]]
    warnings: List[str]


class SubsystemSignalBinding(TypedDict, total=False):
    signal_name: str
    node_logic_id: str
    port_index: int
    page_id: str
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
    node_instances: List[SubsystemPlanNode]
    edges: List[SubsystemPlanEdge]
    imported_signals: List[SubsystemSignalBinding]
    exported_signals: List[SubsystemSignalBinding]
    constraints: List[Dict[str, Any]]
    unresolved_items: List[Dict[str, Any]]
    reasoning: str


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
        "node_instances": [],
        "edges": [],
        "imported_signals": [],
        "exported_signals": [],
        "constraints": [],
        "unresolved_items": [],
        "reasoning": "",
    }
