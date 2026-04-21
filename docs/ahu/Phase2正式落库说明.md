# Phase 2 正式落库说明

> 更新时间：2026-04-09  
> 适用范围：前三阶段整改后的正式 AHU 资产构建、落盘、写库、回滚与烟测流程。

## 1. 结论先定死

- `AHU程序/flows_*.json` 是正式源资产。
- `AHU程序/pattern_library/` 是正式可审阅的结构化产物。
- `outputs/chroma_db/` 是正式运行时 Chroma 目标目录。
- `outputs/chroma_db/` 的定位是 **可重建缓存**，不是版本管理中的正式参考库。
- 仓库根目录下已有的 `chroma_db/` 视为历史遗留产物，不再作为本说明的正式写库目标。

## 2. 当前正式基线文件

当前纳入正式构建基线的源文件为：

- `AHU程序/flows_20251210190941.json`
- `AHU程序/flows_20251229175702.json`
- `AHU程序/flows_20260206160555.json`

构建脚本会按 `flows_*.json` 自动收集。若目录缺失、没有匹配文件、或全部文件都无法解析出有效流程对象，构建会直接失败，不允许静默产出空资产。

## 3. 正式命令

### 3.1 只重建 pattern_library

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py
```

默认输出：

- `AHU程序/pattern_library/subflow_templates.json`
- `AHU程序/pattern_library/system_patterns.json`
- `AHU程序/pattern_library/manifest.json`

### 3.2 正式写入 Chroma

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --write-chroma
```

默认写入：

- `outputs/chroma_db/`

默认 collection：

- `ahu_subflow_templates_v1`
- `ahu_system_patterns_v1`

### 3.3 指定临时目录做烟测

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir outputs/test_tmp/pattern_library_phase2_smoke --write-chroma --persist-dir outputs/test_tmp/chroma_phase2_smoke
```

## 4. manifest 追溯字段

每次构建后的 `manifest.json` 至少记录：

- 构建时间
- 构建脚本与版本
- `system_type`
- `flows_dir`
- `pattern_library_dir`
- 每个源 `flows_*.json` 的：
  - 文件名
  - 路径
  - `sha1`
  - 修改时间
  - 文件大小
  - 解析对象数量
- `subflow_template_count`
- `system_pattern_count`
- 目标 `persist_dir`
- 目标 `collection_names`
- embedding provider / model
- collection owner
- stale cleanup 策略
- 实际写入数量

## 5. collection 独占约束

`write_assets_to_chroma()` 会做 stale ID 清理，因此正式 collection 必须满足“独占”前提：

- `ahu_subflow_templates_v1` 只能写 `subflow_templates`
- `ahu_system_patterns_v1` 只能写 `system_patterns`
- 不能把其他实验资产混写进这两个 collection

代码已经为 collection 写入 owner / asset_key 元数据；若发现目标 collection 不属于当前 Phase 2 AHU 资产链，会直接报错，而不是继续删除旧数据。

## 6. 回滚方式

因为正式 Chroma 目录的定位是可重建缓存，回滚方式固定为：

1. 删除目标目录，例如 `outputs/chroma_db/`
2. 用正式命令重新构建并写库

```powershell
conda activate midea
Remove-Item -Recurse -Force outputs/chroma_db
python scripts/build_phase2_retrieval_indexes.py --write-chroma
```

不要手工修改 `outputs/chroma_db/` 内部文件。

## 7. 烟测要求

至少保留下面这条运行态烟测：

```powershell
conda activate midea
python -m unittest tests.test_phase2_production_chroma_smoke
```

这条烟测覆盖：

- 真实读取 `AHU程序/flows_*.json`
- 真实生成 `pattern_library`
- 真实写入 Chroma
- 真实初始化 `RetrievalAgent`
- 真实检索 `subflow_templates` 与 `system_patterns`

## 8. 源资产治理口径

- 新增或替换 `flows_*.json` 后，必须重新执行正式构建命令。
- 提交源资产变更时，至少同时检查：
  - `pattern_library` 是否成功更新
  - `manifest` 中源文件 hash 是否变化符合预期
  - 运行态烟测是否通过
- 若某个源 flow 被移除，重建后对应 stale 模板/模式会从正式 collection 中一起清理。

## 9. 当前统一口径

从本说明起，正式 Phase 2 资产链口径只有一条：

`AHU程序/flows_*.json -> AHU程序/pattern_library -> outputs/chroma_db`

后续 Phase 3/Phase 4 的真实检索与规划回归，应以这条链路为默认基线，而不是继续依赖历史根目录 `chroma_db/` 或临时私有目录。

