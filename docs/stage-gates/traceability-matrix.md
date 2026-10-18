# 需求追溯矩阵（FR/NFR → 实现 → 测试 → 证据 → 当前判定）

> 判定口径：PASS=本轮有实跑证据；HIST=仅有历史报告、本轮未重跑；GAP=无证据或功能缺失。
> 本表由 Agent 依据代码文件名、已读代码片段和本轮日志整理，未逐行审阅全部实现，细节以源码为准。
> 最近更新：S02/S03/S04 完成后。不带 key 的一键回归为 23 个脚本、352 项通过、0 失败（evidence/s03_verify_all_nokey_run3.log；S02 修改 classify.py 后复跑结果相同）。

| 需求 | 实现文件 | 测试/验证 | 最近证据 | 判定 |
|---|---|---|---|---|
| FR-1 文件导入（5 格式） | app/parsers.py, main.py(upload, 5MB 上限) | verify_v02.py | s03_verify_all_nokey_run3.log | PASS |
| FR-2 文本粘贴 | main.py(/documents/text) | verify_v03.py, verify_admin_ui2.py | s01_admin_ui2.log（11/11） | PASS |
| FR-3 悬浮框 | floatbox/ | verify_floatbox*.py | s11_floatbox_e2e.log（6/6，仅记事本） | 自动化 PASS；浏览器/Word/微信人工验收 GAP（S11 BLK-01，需用户本人） |
| FR-4~6 摘要/分类/标签 | app/llm.py, classify.py, pipeline.py | verify_v04.py, verify_llm_real.py, eval_classify_stability.py | s10_llm_real_rerun.log（14/14）；s02_eval_classify_stability.md（真实 deepseek + local 嵌入：20 篇，复用 15/15，创建分类 8，needs_review 0） | PASS；分类稳定性为单次运行小样本；摘要质量未人工评估：GAP |
| FR-5 分类路径规范化 | classify.py normalize_path | eval_classify_stability.py | S02 评估暴露全角冒号重复分类（12 个分类），修复后降为 8 | PASS（缺陷已修复；回归 0 失败） |
| FR-7 切片与向量化 | app/embedding.py, vectorstore.py | verify_v04/v05 | s03_verify_all_nokey_run3.log | PASS |
| FR-8/9 混合检索与过滤 | app/hybrid.py | verify_v05~v07, eval_retrieval_groups.py | s02_eval_retrieval_groups.md（18 查询分四组） | 功能 PASS；评估为小语料单次运行 |
| FR-10 文档增删改查 | main.py, manage.py | verify_v08.py, verify_admin_ui.py | s03_verify_all_nokey_run3.log | PASS |
| FR-11 手动修正 | main.py(PATCH), corrections | verify_v14.py | s03_verify_all_nokey_run3.log | PASS（反馈增益不宣称） |
| FR-12 分类树管理 | manage.py, main.py(/categories) | verify_v08.py, verify_admin_ui2.py | s01_admin_ui2.log | API PASS；UI 无分类合并：GAP |
| 状态机与重试 | pipeline.py(recover, reprocess) | verify_v04.py, verify_recover.py | s03_verify_all_nokey_run2.log（12/12） | PASS；为状态模拟，未真实 kill 进程 |
| NFR-1/2 本地与隐私 | 管理页运行模式提示 | verify_admin_ui2.py | s01_admin_ui2.log | PASS |
| NFR-3 性能（1 万文档） | numpy 暴力余弦 | eval_perf.py | s03_eval_perf.md：10k 文档/5 万切片，混合检索 P50 607ms / P95 646ms | PASS（Mock 向量、合成语料、单机单次；P95 接近 1 秒；不含真实 bge 查询嵌入耗时） |
| 备份与恢复 | scripts/kb_backup.py | verify_backup.py（13 项） | s03_verify_all_nokey.log | PASS（仅手动备份，无定时/增量/加密） |
| 重复导入（content_hash） | db.py, main.py | verify_duplicate.py（9 项） | s03_verify_all_nokey_run3.log | PASS（策略为“告知不合并”，返回 duplicate_of） |
| 交付与复现 | README.md, start_*.bat, requirements.lock.txt | S04 契约 AC-01~03 | docs/stage-gates/reports/S04-gate-report.md | PASS（仅本机已有 venv；干净机器复现与 Docker 构建未验证） |

## 当前未关闭问题
1. BLK-01（P1）：悬浮框第三方应用（浏览器、Word、微信）人工验收，只能由用户本人完成（S11）。
2. GAP：摘要/标签/分类的人工质量评估（需用户抽检）；摘要自动指标（ROUGE）不能代表质量。
3. GAP：管理页无分类合并 UI；未做多浏览器人工验收。
4. GAP：干净机器从零安装复现、Docker 镜像构建未验证。
5. 启动恢复在 startup 中同步执行、reprocess 同步阻塞，真实 LLM 下可能拖慢，未实测。
6. 评估均为单次运行、小语料、无置信区间；同义改写组中混合检索 R@1（0.83）低于纯语义（1.00），误例见 s02_eval_retrieval_groups.md。
7. 竞品对比三项“待核实”。
8. evidence 目录中 s02_eval_classify_stability_real.md/.err 为 EMBEDDING_MODE 取值错误时的失败产物，已作废（DEBT-08），引用以 s02_eval_classify_stability.md 为准。
9. DEBT-04（P2）：本轮使用的 DeepSeek key 已多次出现在聊天记录，演示或提交后应作废并重新生成。
