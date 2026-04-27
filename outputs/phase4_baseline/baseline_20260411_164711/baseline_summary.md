# Phase 4 Baseline Summary

- ????: 2026-04-11T16:49:19
- ????: 2026-04-11
- ????: D:\yjsproject\midea\outputs\phase4_baseline\baseline_20260411_164711
- CHROMA_PERSIST_DIR: D:\yjsproject\midea\chroma_db
- Collections: ahu_subflow_templates_v1, ahu_system_patterns_v1, kong_modules_v1

## ????

- 为 AHU 生成送风机标准控制
- 为 AHU 生成送风机与电加热联动控制
- 为 AHU 生成送风机、冷水阀与电加热联动控制

## ????

- kong_modules_v1: True
- ahu_subflow_templates_v1: True
- ahu_system_patterns_v1: True

## ????

- phase3_tests_initial: FAILED(1)
  note: Initial subprocess run failed once during baseline generation.
  ??: FAILED (failures=1)
- phase2_tests: OK
  ??: OK
- phase1_tests: OK
  ??: OK
- runtime_tests: OK
  ??: OK
- phase2_production_chroma_smoke: OK
  ??: OK
- pip_check: OK
  ??: No broken requirements found.
- phase3_tests_rerun: OK
  note: Immediate rerun after baseline generation.
  ??: OK

## ????

- [1] 为 AHU 生成送风机标准控制
  verification_status: passed
  repair_scope: none
  route_decision: accept
  trace_dir: D:\yjsproject\midea\outputs\workflow_trace_20260411_164841
- [2] 为 AHU 生成送风机与电加热联动控制
  verification_status: passed
  repair_scope: none
  route_decision: accept
  trace_dir: D:\yjsproject\midea\outputs\workflow_trace_20260411_164858
- [3] 为 AHU 生成送风机、冷水阀与电加热联动控制
  verification_status: passed
  repair_scope: none
  route_decision: accept
  trace_dir: D:\yjsproject\midea\outputs\workflow_trace_20260411_164917

## ??

- AHU collections were missing from ./chroma_db before baseline generation and were rebuilt into the active persist dir.
- The first phase3 subprocess run failed once, but an immediate rerun passed.
