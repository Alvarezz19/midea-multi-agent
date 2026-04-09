# 知识库构建与结构说明

> 最后核对时间：2026-04-09  
> 核对范围：`config.py`、`agents/retrieval_agent.py`、`utils/ahu_knowledge_builder.py`、`utils/knowledge_base_manager.py`、`scripts/build_phase2_retrieval_indexes.py`、`tests/test_phase2_*.py`、`tests/test_phase3_workflow.py`

## 1. 当前知识库在工作流里的角色

当前仓库的知识库不是单一 collection，而是两层资产一起工作：

1. 原子模块知识库：来自 `schemas/*.json`
2. AHU 资产知识库：来自 `AHU程序/flows_*.json`

它们最终共同服务 `RetrievalAgent`，并以 `retrieval_bundle` 的形式进入 Phase 3 主链。

```text
schemas/*.json
AHU程序/flows_*.json
  -> 构建 / 写库
  -> Chroma collections
  -> RetrievalAgent.retrieve_bundle()
  -> retrieval_bundle
  -> ArchitecturePlanner / SubsystemPlanner / GlobalAssembler / CodingAgent
```

`retrieval_context` 仍然存在，但只是从 bundle 派生出来的兼容视图。

## 2. 当前数据源边界

### 2.1 原子模块

来源：`schemas/*.json`

主要字段：

- `module_type`
- `category`
- `name`
- `description`
- `keywords`
- `usage_guides`
- `parameters_schema`
- `ports_definition`
- `template_json`

用途：

- 规则检索
- 原子 fallback
- 编译时模板与端口信息消费

### 2.2 AHU 子流程模板与 system pattern

来源：`AHU程序/flows_*.json`

构建后产出两类正式资产：

- `subflow_templates`
- `system_patterns`

这些资产既会写到 `pattern_library` 目录，也可以写入正式 Chroma collections。

## 3. 当前正式 collections

默认配置见 `config.py`：

| 配置项 | 当前默认值 | 说明 |
|:---|:---|:---|
| `CHROMA_PERSIST_DIR` | `./outputs/chroma_db` | 正式 Chroma 持久化目录 |
| `CHROMA_COLLECTION_ATOMIC_MODULES` | `kong_modules_v1` | 原子模块 collection |
| `CHROMA_COLLECTION_SUBFLOW_TEMPLATES` | `ahu_subflow_templates_v1` | AHU 子流程模板 collection |
| `CHROMA_COLLECTION_SYSTEM_PATTERNS` | `ahu_system_patterns_v1` | AHU system pattern collection |
| `PHASE2_CHROMA_COLLECTION_OWNER` | `phase2_ahu_assets` | Phase 2 正式资产集合所有者标识 |
| `AHU_PATTERN_LIBRARY_DIR` | `AHU程序/pattern_library` | 规范化导出目录 |

## 4. 当前正式产物与写库口径

### 4.1 只生成规范化产物

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir AHU程序/pattern_library
```

### 4.2 生成并写入正式 Chroma

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir AHU程序/pattern_library --write-chroma --persist-dir outputs/chroma_db
```

### 4.3 当前冻结口径

- `pattern_library` 是可重建缓存，不是唯一事实源。
- 正式写库目标默认是 `outputs/chroma_db`。
- manifest 会记录：
  - `build_command`
  - `persist_dir`
  - `collection_names`
  - `collection_owner`
  - `asset_chain_role = rebuildable_cache`
  - 源 `flows_*.json` 摘要
- `write_assets_to_chroma()` 已支持 stale ID 清理与 collection owner 校验，避免重复构建时残留过期资产。

## 5. Retrieval 正式输出边界

当前 Retrieval 正式主输出是 `retrieval_bundle`，其核心结构是：

```json
{
  "atomic_modules": [],
  "subflow_templates": [],
  "system_patterns": [],
  "style_guides": [],
  "metadata": {
    "selected_case_pattern_id": "",
    "retrieved_atomic_count": 0,
    "retrieved_subflow_count": 0,
    "retrieved_pattern_count": 0
  }
}
```

下游正式消费者主要依赖：

- `ArchitecturePlanner.pattern_bindings`
- `SubsystemPlanner` 的模板复用 / atomic fallback
- `GlobalAssembler` 的文档映射
- `CodingAgent` 的编译输入映射

`retrieval_context` 只保留给旧 `PlanningAgent` / `AssemblyAgent` 等 compat 路径。

## 6. 当前边界与限制

- 当前知识库的真实上游事实源是 `schemas/*.json` 与 `AHU程序/flows_*.json`。
- 如果 `flows_*.json` 没有进入版本管理，那么“干净克隆即可复现正式 AHU 资产链”不成立。
- 当前 `pattern_library` 输出目录不应被当作手工编辑后再回写主链的事实源；正式策略是重建而不是手工改缓存。

## 7. 回滚与重建建议

当前资产链采用“重建式回滚”：

1. 保留 `manifest.json` 与 `build_command`
2. 切换到新的 `persist_dir`，或重建目标 `persist_dir`
3. 重新执行 `build_phase2_retrieval_indexes.py`

不建议手工修改 Chroma collections 内容，也不建议绕过 manifest 直接 patch 规范化产物。

## 8. 一句话结论

当前仓库的知识库已经不是“单一模块向量库”，而是“原子模块 + AHU 正式资产链”的组合系统；正式检索输出是 `retrieval_bundle`，正式落库默认目标是 `outputs/chroma_db`，`pattern_library` 只是可重建缓存。
