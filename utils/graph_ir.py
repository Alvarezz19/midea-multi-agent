"""
Phase 1 Graph IR and verification models.

These models establish a stable, strongly-typed intermediate representation
between planning and JSON compilation without forcing the planner to be
rewritten in the same phase.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PageIR(BaseModel):
    """Top-level tab/page definition in the graph."""

    page_id: str
    label: str
    kind: str = "control"
    order: int = 0


class SubflowPortIR(BaseModel):
    """Subflow interface port definition."""

    port_index: int
    name: str = ""
    x: int = 0
    y: int = 0


class SubflowDefinitionIR(BaseModel):
    """Reusable subflow definition."""

    template_id: str
    definition_id: str
    name: str
    inputs: int = 0
    outputs: int = 0
    in_ports: List[SubflowPortIR] = Field(default_factory=list)
    out_ports: List[SubflowPortIR] = Field(default_factory=list)
    template_source: str = "retrieval_template"
    raw_definition: Dict[str, Any] = Field(default_factory=dict)
    internal_flow_objects: List[Dict[str, Any]] = Field(default_factory=list)


class NodeInstanceIR(BaseModel):
    """Node instance inside a page or a subflow."""

    instance_id: str
    logic_id: str
    module_type: str
    page_id: Optional[str] = None
    subflow_id: Optional[str] = None
    template_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, int] = Field(default_factory=dict)
    input_count: int = 0
    output_count: int = 0
    reasoning: str = ""


class EdgeIR(BaseModel):
    """Directed port-level edge between node instances."""

    edge_id: str
    from_instance: str
    from_port: int = 0
    to_instance: str
    to_port: int = 0
    signal_id: str = ""


class SignalIR(BaseModel):
    """Named logical signal derived from edges."""

    signal_id: str
    naming_hint: str = ""
    source: Dict[str, Any] = Field(default_factory=dict)
    targets: List[Dict[str, Any]] = Field(default_factory=list)


class AssembledGraphIR(BaseModel):
    """Phase 1 assembled graph intermediate representation."""

    graph_ir_version: str = "2.0"
    goal: str = ""
    pages: List[PageIR] = Field(default_factory=list)
    subflow_definitions: List[SubflowDefinitionIR] = Field(default_factory=list)
    node_instances: List[NodeInstanceIR] = Field(default_factory=list)
    edges: List[EdgeIR] = Field(default_factory=list)
    signal_registry: List[SignalIR] = Field(default_factory=list)
    layout_hints: Dict[str, Any] = Field(default_factory=dict)
    unresolved_items: List[Dict[str, Any]] = Field(default_factory=list)


class CompileReport(BaseModel):
    """Compiler statistics for acceptance and debugging."""

    node_count: int = 0
    subflow_count: int = 0
    page_count: int = 0
    body_node_count: int = 0
    dropped_node_count: int = 0
    missing_template_count: int = 0
    unresolved_placeholder_count: int = 0
    body_expansion_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class CompiledArtifact(BaseModel):
    """Deterministic compiler output."""

    json_text: str = "[]"
    flow_objects: List[Dict[str, Any]] = Field(default_factory=list)
    id_map: Dict[str, str] = Field(default_factory=dict)
    layout_map: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    compile_report: CompileReport = Field(default_factory=CompileReport)


class VerificationIssue(BaseModel):
    """Single verification finding."""

    issue_id: str
    severity: str
    scope: str
    target_id: str
    rule_id: str
    message: str
    suggested_fix: str = ""
    repair_payload: Dict[str, Any] = Field(default_factory=dict)


class VerificationMetrics(BaseModel):
    """Lightweight structural metrics."""

    missing_required_inputs: int = 0
    isolated_nodes: int = 0
    invalid_port_refs: int = 0


class VerificationReport(BaseModel):
    """Phase 1 rule-first verification report."""

    status: str = "passed"
    repair_scope: str = "none"
    issue_summary: str = ""
    issues: List[VerificationIssue] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metrics: VerificationMetrics = Field(default_factory=VerificationMetrics)
