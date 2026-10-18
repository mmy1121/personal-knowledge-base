# 阶段契约 S10：评估实验与对比材料（对应 MVP 计划 V1.0 前半）

```yaml
stage_id: "S10"
stage_name: "评估实验与对比材料"
objective: "后端功能回归全绿；评估/对比实验可复现；文档中的数字与实际结果文件一致"
derivation: "来源：MVP与迭代计划.md V1.0（评估实验、README、一键验证）；项目说明.md NFR-6；用户要求课程展示需有测试数据佐证。无独立既有阶段契约，按 STAGE_GATE §0.4 推导最小契约。"
scope_in:
  - "work/scripts/verify_*.py 一键回归"
  - "eval_*.py / compare_systems.py 的结果文件与文档数字一致性"
scope_out:
  - "悬浮框在浏览器/Word/微信中的人工体验验收（归入 S11 演示阶段）"
  - "新增业务功能"
next_stage: "S11 演示与交付（MVP/演示 Gate）"
acceptance:
  - id: "AC-01"
    level: "MUST"
    requirement: "一键回归本轮实时执行全部通过，0 失败"
    method: "RUN_COMMAND"
    command: "cd work && venv\\Scripts\\python.exe scripts\\verify_all.py"
    expected: "退出码 0；合计失败 0；脚本数 19"
  - id: "AC-02"
    level: "MUST"
    requirement: "评估结果文件存在，且 README/对比实验结果.md 中引用的关键数字与结果文件一致"
    method: "REVIEW"
    expected: "逐项比对 eval_cmrc_long / eval_real_data / eval_correction_feedback / 对比实验结果 的数字，无不一致"
  - id: "AC-03"
    level: "MUST"
    requirement: "文档中对未验证项（竞品待核实、替身 LLM、单次运行、真实 LLM）如实标注，不宣称未实测结论"
    method: "REVIEW"
    expected: "对比实验结果.md 与 README 含对应局限声明"
  - id: "AC-04"
    level: "SHOULD"
    requirement: "真实 LLM 路径有本轮实测证据"
    method: "RUN_COMMAND"
    command: "cd work && venv\\Scripts\\python.exe scripts\\verify_llm_real.py"
    expected: "需 LLM_API_KEY；无 key 则脚本跳过（计 0 项），此时该项不得记 PASS"
  - id: "AC-05"
    level: "SHOULD"
    requirement: "仓库中无密钥残留"
    method: "RUN_COMMAND"
    command: "grep -rIl -E \"sk-[A-Za-z0-9]{20,}\" 排除 venv/ext_dl/ext_data"
    expected: "无输出"
required_environment:
  - "Windows 11, Python 3.12.10 (work\\venv)"
required_artifacts:
  - "docs/stage-gates/evidence/ 下本轮日志"
  - "S10-gate-report.md / S10-gate-result.json"
risks_and_dependencies:
  - "S11 需要人工验收悬浮框；该项无法由 Agent 自动完成，预期 BLOCKED"
```
