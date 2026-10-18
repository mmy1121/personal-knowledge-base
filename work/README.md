# 个人知识库与分类存储系统

本地部署：文本 / TXT / MD / PDF / DOCX / XLSX 入库 → 摘要、标签、两段式分类、切片向量化 →
jieba 预分词 + SQLite FTS5 关键词检索与向量语义检索（RRF 融合）→ 桌面悬浮框快捷录入。
迭代进度与实测记录见 `../MVP与迭代计划.md`，开源组件核实见 `../核实报告.md`。

## 安装（Windows）

```
cd C:\Users\User\Desktop\111\work
venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 一键启动（Windows）

在 `work` 目录下双击或运行：

```
start_backend.bat      # 启动后端（127.0.0.1:8000），管理页在 http://127.0.0.1:8000/
start_floatbox.bat     # 启动桌面悬浮框（需后端已启动）
```

## 启动后端

```
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

环境变量（均有默认值，默认 Mock，无需 key、无需联网）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DB_PATH` | `data/kb.db` | 数据库单文件 |
| `CORS_ORIGINS` | 本机 5173 端口 | 逗号分隔 |
| `LLM_PROVIDER` | `mock` | 可选 mock / deepseek / openai / ollama；配合 `LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL`（DeepSeek 与 OpenAI 兼容路径已用真实 key 联调通过：scripts/verify_llm_real.py，密钥仅经环境变量传入；Ollama 已用本机 qwen2.5:1.5b 实测通过（OLLAMA_MODEL=qwen2.5:1.5b 时 verify_llm_real.py 共 19 项）） |
| `EMBEDDING_MODE` | `mock` | `local` 使用 fastembed + bge-small-zh（首次需联网下载模型，已实测，维度 512） |
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 仅 `local` 模式使用 |
| `SEM_MIN_SIM` | mock 0.3 / 真实 0.4 | 语义路相似度下限，已用 eval 数据标定 |
| `AUTO_PROCESS` | `1` | 录入后自动后台处理，0 关闭 |
| `KB_API_TOKEN` | 空 | 设置后请求需带 X-KB-Token |
| `CORR_MIN_SIM` | `0.5` | 用户修正反馈的相似度下限 |

启动时会自动重新处理遗留的 `pending/processing` 文档。

## 启动悬浮框

```
venv\Scripts\python.exe -m floatbox.app
```

- 默认热键 `Ctrl+Alt+K` 呼出/隐藏，`Ctrl+Enter` 存入，`Esc` 隐藏。
- 后端未启动或报错时，红色提示且保留已输入文本。
- 后端地址：环境变量 `KB_API_BASE`（默认 `http://127.0.0.1:8000`）。

## 接口

统一响应 `{"code": 200, "msg": "success", "data": {}}`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/documents/text | 录入文本（`text`、可选 `title`、`source_type`） |
| POST | /api/v1/documents/upload | 上传 txt/md/pdf/docx/xlsx |
| GET | /api/v1/documents | 列表（分页，不含正文；支持 source_type/category_path/tag/status/time 过滤） |
| GET | /api/v1/documents/{id} | 详情（含正文） |
| PATCH | /api/v1/documents/{id} | 改标题/分类/标签（记入 corrections） |
| DELETE | /api/v1/documents/{id} | 级联删除 |
| POST | /api/v1/documents/{id}/reprocess | 失败重试 |
| POST | /api/v1/search | 混合检索（`query`、`limit`、`filters.source_type/category_path/tag/time_from/time_to`） |
| GET/POST | /api/v1/categories | 分类树 / 新建 |
| PATCH | /api/v1/categories/{id} | 重命名（`name`）或合并（`merge_into`） |
| DELETE | /api/v1/categories/{id} | 删除（有文档需 `migrate_to`） |
| GET | /api/v1/tags | 标签列表 |
| GET | /api/v1/health | 健康检查 |

## 验证脚本

在 `work` 目录下运行：

```
venv\Scripts\python.exe scripts\verify_all.py        # 一键运行全部验证并统计
venv\Scripts\python.exe scripts\verify_v01.py        # 单个脚本，v01~v08、verify_floatbox 同理
venv\Scripts\python.exe scripts\eval_fts_tokenizers.py   # 评估：FTS5 分词方案对比
```

最近一次一键验证（不带 key）：23 个脚本、352 项通过、0 失败（verify_llm_real.py 无 LLM_API_KEY 时自动跳过，计 0 项）（含悬浮框 UI/E2E、管理页、备份恢复 verify_backup.py、强杀恢复 verify_recover.py、重复导入 verify_duplicate.py）。证据见 `../docs/stage-gates/evidence/`。

## 评估

- `scripts/eval_semantic.py`：12 篇小语料，近义查询 bge-small-zh Recall@3/MRR=1.00，Mock 与词面基线 0.56。
- `scripts/eval_real_data.py`：今日头条 1500 篇、300 查询，Recall@5：关键词 0.167 / 语义 0.270 / 混合 0.263，混合 MRR 最高 0.192（结果见 `eval_real_data_result.md`）。

- `scripts/eval_llm_classify.py`：真实 DeepSeek 对头条数据集 15 类各 4 条共 60 条做分类，准确率 45/60 = 0.750（调用失败 0）；国际类 0/4 被误判为故事，头条类别本身存在重叠（股票/财经、故事/文化），属保守估计，详见 `eval_llm_classify_result.md`。
- `scripts/eval_cmrc_long.py`：公开数据集 jinaai/longcontext-cmrc2018-zh（1149 篇长文本语料，300 条自然语言问题，每问有标准答案文档）。Recall@5：关键词 0.990 / 语义 0.837 / 混合 0.943；MRR：0.891 / 0.720 / 0.826。问题与原文用词高度重合，关键词路占优，与头条数据集（用词不同，语义路占优）形成互补对照，结果见 `eval_cmrc_long_result.md`。
- `scripts/eval_summary_lcsts.py`：LCSTS 公开摘要集（valid.jsonl，8685 条带参考摘要）抽 50 条，Mock 基线（取开头 100 字）ROUGE-1 召回 0.644 / F1 0.204，真实 DeepSeek 为 0.633 / 0.200，ROUGE-2 F1 0.128 / 0.116。参考摘要仅约 18 字、本系统摘要约 100 字，字级 ROUGE 对长摘要不利且无法体现语义概括质量，该结果只说明 DeepSeek 在此指标上未优于开头截取，不能据此判定摘要质量，需人工抽检或 LLM 评审补充，详见 `eval_summary_lcsts_result.md`。

- `scripts/eval_retrieval_groups.py`：按查询类型分组（关键词重合 / 同义改写 / 长问句 / 专有名词，共 18 条查询、16 篇语料，真实 bge-small-zh）。全部查询 R@1：关键词 0.83 / 语义 0.83 / 混合 0.94，MRR 0.83 / 0.89 / 0.97。同义改写组关键词仅 0.50，语义 1.00，混合 R@1 0.83（误例“下周会不会变冷”：关键词路无命中，混合排名被拉低到第 2）；专有名词组语义 R@1 仅 0.25，混合 1.00，说明两路互补。小语料单次运行，无置信区间，证据见 `../docs/stage-gates/evidence/s02_eval_retrieval_groups.md`。
- `scripts/eval_classify_stability.py`：5 个主题 × 4 篇共 20 篇，真实 DeepSeek + 本地 bge。评估暴露缺陷：LLM 返回的分类路径带全角冒号，导致重复分类（创建 12 个，复用 11/15）；在 `app/classify.py` 增加路径规范化后，创建 8 个分类（5 个主题对应 3 个一级 + 5 个二级），复用 15/15 = 1.00，同类聚合度均为 1.00，needs_review 为 0。单次运行、小样本，不代表大规模稳定性。Mock 结果仅验证机制。
- `scripts/eval_perf.py`：合成语料 + Mock 向量。1k 文档/5k 切片混合检索 P50 60.8ms / P95 68.5ms；10k 文档/5 万切片 P50 607.4ms / P95 645.9ms（满足亚秒级，但 10k 档裕量有限，暴力余弦随切片数线性增长）。未含真实 bge 查询向量化耗时，证据见 `../docs/stage-gates/evidence/s03_eval_perf.md`。
- 重复导入：相同正文（按 SHA-256 判定，忽略首尾空白）仍会入库，响应返回 `duplicate_of`，不覆盖已有文档的人工分类与标签（`scripts/verify_duplicate.py`，9 项）。强杀恢复由 `scripts/verify_recover.py`（12 项）通过状态模拟验证，未真实 kill 进程。

- `scripts/eval_retrieval_groups.py`：16 篇小语料、18 条查询，按关键词重合 / 同义改写 / 长问句 / 专有名词分组，对比关键词、语义（真实 bge-small-zh）、混合三路（R@1/5/10、MRR、nDCG@10）。全部查询 R@1：关键词 0.83 / 语义 0.83 / 混合 0.94。同义改写组语义 R@1 为 1.00，混合为 0.83（误例「下周会不会变冷」关键词路无命中，混合排名第 2）；专有名词组语义 R@1 仅 0.25，混合 1.00。单次运行、小语料，无置信区间，证据见 `../docs/stage-gates/evidence/s02_eval_retrieval_groups.md`。
- `scripts/eval_classify_stability.py`：20 篇 / 5 主题，真实 DeepSeek + 本地 bge 评估自组织分类。评估暴露 LLM 返回路径带全角冒号（如 `生活/烹饪：`）导致重复分类（创建 12 个、复用率 0.73），已在 `classify.py` 加入路径规范化；修复后创建 8 个（含 3 个父级分类）、复用率 15/15、各主题聚合度 1.00。单次运行、小样本；Mock 结果只验证机制。证据见 `../docs/stage-gates/evidence/s02_eval_classify_stability.md`。
- `scripts/eval_perf.py`：合成语料 + Mock 向量下的混合检索延迟。1k 文档 / 5k 切片 P50 60.8ms / P95 68.5ms；10k 文档 / 5 万切片 P50 607.4ms / P95 645.9ms，满足亚秒级目标但 10k 档裕量有限；未含真实模型的查询嵌入耗时，单机单次运行。证据见 `../docs/stage-gates/evidence/s03_eval_perf.md`。
- 重复导入：相同正文（按 SHA-256 判定，忽略首尾空白）仍会入库，响应返回 `duplicate_of`，不覆盖已有文档的人工分类与标签（`scripts/verify_duplicate.py`，9 项）。策略为"告知不合并"，未做自动去重。

- `scripts/eval_retrieval_groups.py`：按查询类型分组（关键词重合/同义改写/长问句/专有名词，共 18 条查询、16 篇语料，真实 bge-small-zh），报告关键词/语义/混合三路 R@1/5/10、MRR、nDCG@10。全部查询 R@1：关键词 0.83 / 语义 0.83 / 混合 0.94；专有名词组语义路 R@1 仅 0.25，混合 1.00；同义改写组混合 R@1 0.83 低于纯语义 1.00（误例：「下周会不会变冷」，关键词路无命中，RRF 拉低了排名）。小语料单次运行，无置信区间，证据见 `../docs/stage-gates/evidence/s02_eval_retrieval_groups.md`。
- `scripts/eval_classify_stability.py`：5 主题 × 4 篇共 20 篇，真实 DeepSeek + 本地 bge。评估发现 LLM 返回的分类路径带全角冒号（如「生活/烹饪：」）导致重复建类（修复前创建 12 个分类、复用率 0.73），已在 `classify.normalize_path` 规范化；修复后创建 8 个分类（含 3 个父级）、复用率 15/15 = 1.00、同类聚合度均为 1.00。单次运行、小语料；Mock 结果只验证机制。证据见 `../docs/stage-gates/evidence/s02_eval_classify_stability.md`。
- `scripts/eval_perf.py`：合成语料 + Mock 向量（不含真实 bge 查询嵌入耗时）。1k 文档/5k 切片混合检索 P50 60.8ms / P95 68.5ms；10k 文档/5 万切片 P50 607.4ms / P95 645.9ms，满足亚秒级，但 10k 档已接近上限，暴力余弦随切片数线性增长。证据见 `../docs/stage-gates/evidence/s03_eval_perf.md`。

## 重复导入

相同正文（按 SHA-256 判定，忽略首尾空白）再次录入时，仍会入库、不丢数据，响应中返回 `duplicate_of`（首篇文档 id），不覆盖已有文档及其人工修正的分类/标签；系统只告知，是否保留由用户决定（`scripts/verify_duplicate.py`，9 项）。

## 备份

数据即 `data/kb.db` 单文件。推荐使用自带工具 `scripts/kb_backup.py`（基于 SQLite Backup API，后端运行时也能得到一致快照，备份后与恢复前均执行 `integrity_check`）：

```
venv\Scripts\python.exe scripts\kb_backup.py backup  data\kb.db backup\kb-20261018.db
venv\Scripts\python.exe scripts\kb_backup.py check   backup\kb-20261018.db
venv\Scripts\python.exe scripts\kb_backup.py restore backup\kb-20261018.db data\kb.db
```

- 备份文件已存在时拒绝覆盖；恢复时若目标库已存在，会先另存为 `.bak` 副本；损坏的备份会被拒绝恢复。
- 恢复前建议先停止后端。自动化验证见 `scripts/verify_backup.py`（13 项）。
- 也可手动使用 `sqlite3 kb.db ".backup backup.db"`。

## 已知限制

- DeepSeek / OpenAI 兼容 Provider 已真实联调通过（14 项）；DeepSeek / OpenAI 兼容 / Ollama 三种 Provider 均已真实联调（Ollama 使用 qwen2.5:1.5b，19 项通过）；Mock 向量是哈希词袋，语义效果以真实 bge 评估为准。
- 向量库为 float16 BLOB + numpy 暴力余弦（规格允许的兜底），未使用 sqlite-vec。
- 悬浮框热键与焦点已有自动化 E2E，但尚未在浏览器、Word 等第三方应用中人工验收。
- wangfenjin/simple 扩展（v0.7.1 Windows x64，SHA256 已校验）加载实测通过：`scripts/eval_simple_ext.py`，18 条查询 Recall@5 / MRR 均为 1.00，与 jieba 预分词持平；仅作可选对照，默认方案仍为 jieba 预分词（无需加载扩展）。结果见 `评估结果_simple扩展对照.md`。
- 最小管理页位于 `/`（`app/static/index.html`），覆盖运行模式显示（Mock/本地/云端是否外发文本）、文本粘贴、文件上传（TXT/MD/PDF/DOCX/XLSX，上限 5MB）、搜索、列表、详情、改标题/分类/标签、重新处理、删除、分类树新建/重命名/删除；浏览器自动化见 `scripts/verify_admin_ui.py`、`verify_admin_ui2.py`。仍为静态单页，未做分类合并等 UI，也未在多浏览器人工验收。
- token 鉴权为可选：设置环境变量 `KB_API_TOKEN` 后，除 `/api/v1/health` 与 CORS 预检外，请求须带 `X-KB-Token`（悬浮框会自动携带）；默认不设置。Host 头始终限制为本机以防 DNS rebinding。
- corrections 已参与自动分类：新文档若与「被用户改过分类的相似文档」相似度≥CORR_MIN_SIM（默认 0.5），其修正目标分类会置顶进入候选，最终仍由 LLM 定夺（verify_v14.py，8 项）。已用头条数据集量化（eval_correction_feedback.py）：仅在修正样本极少时有微弱正收益，样本增多后无增益甚至略降，机制已验证正确，但不宣称提升准确率。
- `scripts/compare_systems.py`：与其他检索范式对比（笔记软件式 unicode61 关键词 / 纯向量 RAG 式 / 本系统混合 RRF），含 cmrc 与头条两个数据集，另有「LLM 全故障时的数据安全」实验；结果与 NotebookLM 已核实限制的功能对比见 `../对比实验结果.md`。竞品为范式基线而非产品实测，未做多随机种子置信区间。
- `scripts/eval_correction_feedback.py`：修正反馈量化（头条 15 类，300 篇测试，LLM 为总选首位候选的确定性替身，只评估候选排序机制）。K=每类被用户修正的篇数：K=1 关闭 0.350 / 开启 0.387（+0.037）；K=3 0.583 / 0.560（-0.023）；K=5 0.670 / 0.637（-0.033）。结论：修正反馈只在修正样本极少时有微弱正收益，样本变多后不优于纯向量候选（centroid 已能覆盖），差异在单次运行的噪声范围内，不能据此宣称提升准确率；K=0 为 0 是因为无任何分类可选，仅作起点。结果见 `eval_correction_feedback_result.md`。

## 交付物与打包排除

提交或打包课程设计时，应包含：`app/`、`floatbox/`、`scripts/`、`requirements.txt`、`requirements.lock.txt`（pip freeze 锁定版本，用于精确复现）、`start_backend.bat`、`start_floatbox.bat`、`.env.example`、`Dockerfile`、`docker-compose.yml`、`README.md`，以及上级目录的各份评估与对比文档。

以下目录或文件不得打包（已在 `.gitignore` 中排除）：

- `venv/`：本机虚拟环境，可按安装一节重建。
- `ext_dl/`：Ollama 安装包与模型等外部下载物，约 1.5GB。
- `ext_data/`：公开评估数据集，可按 `数据集调研.md` 重新下载。
- `data/`：本机数据库，含个人录入内容。
- `.env`：含 API key，禁止分享。
