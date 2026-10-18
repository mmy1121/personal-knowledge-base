# 阶段契约 S11：演示与交付（MVP/演示 Gate）

```yaml
stage_id: "S11"
stage_name: "演示与交付"
objective: "核心用户流程可从头到尾在目标机器（本机 Windows 11）运行；关键体验经人工抽验；交付物清单明确"
derivation: "来源：STAGE_GATE §7 MVP/演示 Gate；MVP与迭代计划.md V0.1 悬浮框人工验收条款；项目说明.md FR-3 验收 1~4；S10 契约 risks 中预告该阶段人工验收项预期 BLOCKED。"
scope_in:
  - "后端真实启动 + 健康检查"
  - "悬浮框→后端→入库→检索 的真实端到端（自动化部分）"
  - "悬浮框在第三方应用中的人工验收"
  - "交付物与打包排除项核对"
scope_out:
  - "新增业务功能"
  - "正式交付级部署/回滚（课程设计不要求）"
next_stage: "无（最终交付）"
acceptance:
  - id: "AC-01"
    level: "MUST"
    requirement: "后端可在目标环境真实启动并响应健康检查"
    method: "RUN_COMMAND"
    command: "cd work && venv\\Scripts\\python.exe -m uvicorn app.main:app --port <临时端口>；curl /api/v1/health"
    expected: "返回成功的统一响应格式"
  - id: "AC-02"
    level: "MUST"
    requirement: "悬浮框→后端→入库 自动化端到端通过"
    method: "RUN_COMMAND"
    command: "cd work && venv\\Scripts\\python.exe scripts\\verify_floatbox_e2e.py"
    expected: "全部通过，0 失败"
  - id: "AC-03"
    level: "MUST"
    requirement: "悬浮框在浏览器/Word/微信等第三方应用中热键唤起、聚焦、Ctrl+Enter 存入的人工验收"
    method: "MANUAL"
    expected: "用户本人确认通过；Agent 无法在真实第三方应用前操作，无用户确认证据则 BLOCKED"
  - id: "AC-04"
    level: "SHOULD"
    requirement: "交付物清单与打包排除项在 README 中说明（排除 ext_dl、ext_data、venv、data、.env）"
    method: "REVIEW"
    expected: ".gitignore 与 README 含对应说明"
required_environment:
  - "Windows 11, Python 3.12.10 (work\\venv)"
required_artifacts:
  - "docs/stage-gates/evidence/ 下本轮日志"
  - "S11-gate-report.md / S11-gate-result.json"
risks_and_dependencies:
  - "AC-03 依赖用户本人操作；无法自动化"
```
