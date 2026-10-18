# S10 阶段验收报告：评估实验与对比材料

- 结论：**CONDITIONAL_PASS**（can_advance=true）
- 验证时间：2026-10-18T12:14:19+08:00
- 环境：Windows 11 / Python 3.12.10；无 Git 仓库，未捏造 SHA
- independent_verification: **false**（同一工作流在独立验证步骤中重新运行并核对产物）

| 编号 | 级别 | 结果 | 证据 |
|---|---|---|---|
| AC-01 一键回归 | MUST | PASS | 本轮实跑：19 脚本，307 通过，0 失败，退出码 0（evidence/verify_all_run1.log） |
| AC-02 数字一致 | MUST | PASS | 与结果文件快照逐项一致；对比实验延迟列因分次运行略有差异 |
| AC-03 如实标注 | MUST | PASS | 局限声明齐全 |
| AC-04 真实 LLM | SHOULD | PASS | 用户提供新 key，仅经进程环境变量传入，补测 verify_llm_real.py：14/14 通过，退出码 0（evidence/s10_llm_real_rerun.log）；首次 verify_all 时无 key 计 0 项 |
| AC-05 无密钥残留 | SHOULD | PASS | 扫描无命中 |

## 遗留（登记）
1. DEBT-01 已关闭（AC-04 补测通过）。注意：该 key 已出现在聊天记录中，演示/提交后应作废。
2. DEBT-02（P2）：竞品三项待核实；实验单次运行。

## 未验证项
本轮没有重跑 eval_*.py（评估结果为此前运行产生，仅核对文档与结果文件一致）；悬浮框第三方应用人工验收归入 S11。
