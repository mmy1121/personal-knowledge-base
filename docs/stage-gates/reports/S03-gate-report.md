# S03 阶段验收报告（精简版）：可靠性——备份与恢复

- 验证时间：2026-10-18
- 环境：Windows 11 / Python 3.12.10；无 Git 仓库
- independent_verification: **false**（同一工作流重新运行并读取产物）

| 编号 | 级别 | 结果 | 证据 |
|---|---|---|---|
| AC-01 备份为时间点快照、integrity_check 通过、拒绝覆盖已有备份 | MUST | PASS | verify_backup.py 13 通过 / 0 失败 |
| AC-02 恢复后内容一致、覆盖前保留原库副本、损坏备份被拒绝且目标库不变 | MUST | PASS | 同上 |
| AC-03 一键回归含新脚本且 0 失败（不带 key） | MUST | PASS | evidence/s03_verify_all_nokey.log：21 个脚本，331 通过，0 失败，退出码 0；补充 verify_recover.py 后复跑 evidence/s03_verify_all_nokey_run2.log：22 个脚本，343 通过，0 失败，退出码 0 |
| 补充：强杀后 pending/processing 文档可由启动恢复处理（计划 S03 强制项） | MUST（计划） | PASS | verify_recover.py 12 通过 / 0 失败：两种遗留状态均恢复为 stored，已完成文档不重复处理，重复 recover 不产生重复切片，正文未丢失。注意：该脚本通过改写状态模拟强杀，未真实 kill 进程 |
| 补充：重复导入行为界定（计划 S03 content_hash 项） | SHOULD（计划） | PASS | verify_duplicate.py 9 通过 / 0 失败：重复内容仍入库不丢数据，响应返回 duplicate_of，首尾空白不影响判重，重复导入不覆盖已有文档的人工分类与标签，文件上传同样返回 duplicate_of。策略为"告知不合并"，未做自动去重或合并 |
| AC-03 补充：加入 verify_duplicate 后第三轮回归 | MUST | PASS | evidence/s03_verify_all_nokey_run3.log：23 个脚本，352 通过，0 失败，退出码 0 |
| 补充：规模与性能（计划 S03：1k/10k 文档检索 P50/P95） | MUST（计划） | PASS（Mock 向量、合成语料） | evidence/s03_eval_perf.md：1k 文档/5k 切片，混合检索 P50 60.8ms / P95 68.5ms；10k 文档/5 万切片，混合检索 P50 607.4ms / P95 645.9ms，关键词路 P95 20.4ms。均满足规格 NFR-3 的亚秒级目标。注意：10k 档 P95 已接近 1 秒上限，裕量有限；暴力余弦随切片数线性增长，超过约 5 万切片需考虑优化；结果为单机单次运行，使用合成语料与 Mock 向量，未含真实 bge 模型的查询嵌入耗时，不代表真实模型下的端到端延迟 |
| AC-04 仓库无密钥残留 | SHOULD | PASS | evidence/s03_secret_scan.log：无命中；新增脚本与证据文件后复扫（含直接搜索该 key 片段）evidence/s03_final_secret_scan.log：无命中 |

## 说明
- 不带 key 的回归中 verify_llm_real.py 计 0 项（跳过）。真实 LLM 的证据以 S01 第 4 轮带 key 回归（332 项，其中该脚本 14 项）为准，本阶段不重复宣称。
- 本阶段只覆盖备份/恢复工具，未做定时备份、增量备份、加密备份。

## 遗留
1. DEBT-04（P2）：DeepSeek key 已出现在聊天记录中，演示或提交后应作废并重新生成。
2. 悬浮框在第三方应用中的人工验收仍需用户本人完成（S11）。
