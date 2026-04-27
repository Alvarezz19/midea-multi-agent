# 工作流前端 V1

这是工作流 V1 联调用的前端驾驶舱，基于 `Vite + React + TypeScript`。页面只消费 `/api/workflow` 投影 DTO，不读取完整 `WorkflowState` 或磁盘 trace 文件。

## 启动

```powershell
cd frontend
npm install
npm run dev
```

默认 API 地址来自：

```text
VITE_WORKFLOW_API_BASE_URL=http://127.0.0.1:8000
```

如需调整，复制 `.env.example` 为 `.env.local` 后修改。

## 后端联调

在仓库根目录启动后端：

```powershell
conda activate midea
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:5173/workflow
```

FastAPI 默认允许 `http://127.0.0.1:5173` 和 `http://localhost:5173` 跨域访问；如需改端口，设置后端环境变量 `WORKFLOW_CORS_ORIGINS`。

## 页面范围

- `/workflow`：启动页、健康检查、本地最近运行。
- `/workflow/:threadId/:attemptId`：详情页、阶段轨道、诊断、review 卡片、attempt 历史。
- `/workflow/:threadId/:attemptId/result`：最终 `json_text`、`compile_report`、`verification_report`。
- `/workflow/:threadId/:attemptId/debug`：`/trace` 摘要与 `/state-history` 瘦身历史。

## 回归命令

```powershell
cd frontend
npm run typecheck
npm run test
npm run build
```

## 手工验收

1. 进入 `/workflow` 后能看到健康检查结果。
2. 输入 `为 AHU 生成送风机与电加热联动控制`，默认开启架构评审，创建运行后跳转到详情页。
3. `queued / running` 自动轮询；刷新页面后通过 URL 恢复同一 attempt。
4. `interrupted` 时展示 review 卡片，`approve / feedback / clarify / reject` 提交体包含当前 `attempt_id` 与 `review_id`。
5. `feedback / clarify` 缺少反馈说明时前端阻止提交；非法 `updated_constraints` JSON 也会阻止提交。
6. `completed` 后结果页展示 JSON 产物、编译报告和验收报告。
7. Trace 调试页只展示后端投影摘要和瘦身 state-history，不读取磁盘路径。
