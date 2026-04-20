# tests/legacy

这里存放 legacy / compat 回归测试的真实实现。

当前约定：

- `tests/test_*.py` 旧路径可以继续保留为兼容入口
- 真实测试实现优先下沉到 `tests/legacy/`
- 这样既能兼容现有显式回归命令，也能逐步把 legacy 回归与正式合同测试分开

当前已下沉：

- `legacy_execution_plan_compat.py`
- `legacy_agent_imports_compat.py`
- `phase2_planning_bundle_compat.py`
- `phase2_retrieval_bundle_compat.py`
- `phase6_retrieval_eval_compat.py`

已清退：

- `agents/legacy/retrieval_compat.py`
- `agents/legacy/coding_compat.py`
- `phase1_workflow_compat.py`
- `phase2_bundle_consumers_compat.py`
- `phase2_retrieval_agent_compat.py`
- `phase7_coding_determinism_compat.py`

原因：

- 这些文件直接绑定已删除的仓库级 public compat API：
  - `RetrievalAgent.retrieve(...)`
  - `CodingAgent.compile_graph(...)`
  - `CodingAgent.generate_json(...)`
