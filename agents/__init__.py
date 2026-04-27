"""Agent package.

Keep package initialization lightweight so offline tests can import individual
agents without pulling in optional runtime dependencies such as ChromaDB.
"""

__all__ = [
    "analysis_agent",
    "architecture_planner",
    "coding_agent",
    "global_assembler",
    "legacy",
    "retrieval_agent",
    "subsystem_planner",
    "verifier_agent",
]
