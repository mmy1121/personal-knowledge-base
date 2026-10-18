# MVP 与迭代计划

> 原则：每个迭代都能独立运行、独立验证；先打通"录入 → 落库 → 关键词检索"，再逐层叠加 AI 能力。
> 未经实测的第三方库结论一律标注【待实测】，以实测结果为准。

## 一、V0.1 最小可用初代（目标：1~2 天内跑通）

**范围（只做这些）**
1. FastAPI 后端 + SQLite 单文件，建表（documents / document_bodies / FTS5）。
2. `POST /api/v1/documents/text`：落库，status=pending，返回 doc_id。
3. `POST /api/v1/documents/upload`：仅 TXT / MD（先不做 PDF/DOCX/XLSX）。
4. `POST /api/v1/search`：仅关键词检索，jieba 预分词 + FTS5，AND 档 + OR 档 → RRF。
5. `GET /api/v1/documents`、`GET /api/v1/documents/{id}`、`DELETE`。
6. 悬浮框：PySide6 无边框窗口 + Ctrl+Alt+K 全局热键（ctypes RegisterHotKey）+ Ctrl+Enter 存入；失败保留文本。
7. 全部默认 Mock，无需 key、无需联网。

**明确不做**：LLM 摘要/分类/标签、向量、管理页、分类树。

**V0.1 验收（可自动化）**
- `scripts/verify_v01.py`：建表；text/upload 入库；搜"向量数据库"命中"向量数据库选型"；2 字词"分类"可命中；删除后无 FTS 残留。
- 悬浮框人工验收：在浏览器/Word 中按热键能唤起并聚焦；Ctrl+Enter 后数据库新增一条；后端关闭时文本不丢。

## 二、迭代路线

| 版本 | 新增能力 | 关键验证 | 对应任务 |
|---|---|---|---|
| V0.1 | 文本/TXT/MD 入库 + 中文关键词检索 + 悬浮框 | 上述验收 | 1、3、5(关键词) |
| V0.2 | PDF/DOCX/XLSX 解析（扫描 PDF 报错）、切片 | 5 格式样例文件 | 2 |
| V0.3 | 处理流水线骨架：状态机 pending→processing→stored/failed、重试接口、启动恢复；Mock LLM/Embedding | LLM 抛异常文档不丢、可重试 | 4(骨架) |
| V0.4 | 摘要/标签；向量存储（sqlite-vec，失败则 numpy 兜底）；RRF 融合语义路 | Mock 固定向量测融合；真实 bge-small 可选语义用例 | 4、5 |
| V0.5 | 两段式分类 + centroid + 分类树约束 | 分类准确率小样本、token 对比 | 4(分类) |
| V0.6 | 管理接口、分类树管理、corrections 记录、最小管理页 | 增删改查无残留 | 6 |
| V1.0 | 评估实验、README、一键验证、安全（token/CORS） | 全绿 + 实验报告 | 7、8 |

## 三、多 agent 协同工作流

| 角色 | 职责 | 产出 |
|---|---|---|
| 实现 agent | 按当前迭代范围写代码与验证脚本 | 代码 + verify 脚本 |
| 验证 agent | 独立运行验证脚本，不读实现者的"完成"声明，只看结果 | 通过/失败报告 |
| 评审 agent | 对照规格与"实现注意事项"清单找偏差（如 hash() 加盐、AND 过严） | 问题清单 |
| 记录 agent | 把实测结论（库能否加载、许可证）回写到文档，替换【待实测】 | 文档更新 |

循环：实现 → 验证 → 评审 → 修复 → 回写文档；任一环失败不进入下一迭代。

## 四、核实项状态（详见《核实报告.md》）

已完成（实测）：
- [x] sqlite-vec 0.1.9 在 `work\venv`（Python 3.12.10 / SQLite 3.49.1）加载成功，KNN 查询正常。
- [x] FTS5 中文：trigram 搜 2 字词返回 0 条；jieba 预分词对 4 字词、2 字词、英文词均命中。
- [x] 许可证（包元数据）：sqlite-vec MIT/Apache-2.0、jieba MIT、markitdown MIT、fastembed Apache-2.0、ranx MIT、langchain-text-splitters MIT、onnxruntime MIT；pynput 为 LGPLv3（动态使用可接受，课程设计中需在报告注明；也可改用 ctypes RegisterHotKey 规避）。
- [x] 在 venv 中 pip 安装成功：markitdown 0.1.8、fastembed 0.9.0、ranx 0.3.21、pynput 1.8.2（Windows 可用）。
- [x] GitHub API 核实仓库许可证：sqlite-vec Apache-2.0、markitdown MIT、fastembed Apache-2.0、jieba MIT（最近更新 2024-08，维护较慢）、Khoj/Karakeep AGPL-3.0、paperless-ngx GPL-3.0、AnythingLLM MIT、private-gpt Apache-2.0、txtai Apache-2.0；wangfenjin/simple 仓库许可证字段为 NOASSERTION，需查看 LICENSE 原文。
- [x] simple v0.7.1 发布页存在 libsimple-windows-x64.zip（5,473,005 字节）。

未完成（不得当作已验证）：
- [x] simple 扩展实测加载：用户经本机代理（127.0.0.1:7890）续传下载完整 zip，SHA256 与官方 `7f03cc28…bed0b` 一致，解压至 `work\ext_dl\simple_v071`；`scripts/eval_simple_ext.py` 加载成功，在 12 篇语料、18 条查询上 Recall@5 / MRR 均为 1.00，与 jieba 预分词方案持平（小语料，仅证明机制，不代表大规模表现）。结果见 `评估结果_simple扩展对照.md`。
- [x] simple 的 LICENSE 原文已确认（经代理读取 raw.githubusercontent.com）：MIT 与 GPL v3+ 双许可，使用者可任选其一；本项目按 MIT 使用。GitHub API 显示 NOASSERTION 是因为双许可文本未被自动识别。
- [ ] fastembed 对 bge-small-zh 模型的实际下载与推理实测（模型文件需联网下载）。
- [x] V0.2 解析与切片已实测：`scripts/verify_v02.py` 20/20 通过（TXT-GBK、MD、DOCX 段落+表格、XLSX 多 sheet 分区、PDF 文本层、扫描 PDF 与旧版 .doc 给提示、损坏 DOCX 不崩溃、切片与重叠、上传集成、上传后可检索）；V0.1 回归 `verify_v01.py` 23/23 通过（旧的"拒绝 PDF"用例已随 V0.2 改为"损坏 PDF 返回 400"）。
- [x] V0.3 处理流水线骨架已实测：`scripts/verify_v03.py` 22/22 通过（状态机 pending→processing→stored/failed、LLM 故障转 failed 不抛异常且正文不丢、无摘要时关键词检索仍可用、重试只重做缺失步骤、recover 只处理 pending/processing、`POST /documents/{id}/reprocess` 含 404、应用启动事件自动恢复遗留文档）。本轮 V0.1/V0.2 未改动，回归结果沿用上一轮（23/23、20/20）。
- [x] V0.4（向量部分）已实测：`scripts/verify_v04.py` 27/27 通过（Mock Embedding 用 blake2b 确定性哈希、L2 归一化、float16 BLOB 存储、同模型才比较、维度不一致返回空、Embedding 故障转 failed 且摘要保留、失败无切片残留、重试不重复调用 LLM、重处理不产生重复切片、长文档多切片且结果只出现一次、删除文档后切片向量无残留）。注意：Mock 是哈希词袋，只能验证词面相似，**不能证明语义近义检索**；真实语义验收需用 fastembed + bge-small-zh 单独实测（尚未做）。
- [x] V0.5（混合检索）已实测：`scripts/verify_v05.py` 16/16 通过（关键词 AND 档 + OR 档 + 语义路三路 RRF 融合；两路同时命中者排第一；`filters` 中的来源类型与时间范围过滤；向量路异常或未配向量时自动退化为纯关键词；API 统一格式、空查询 400、无结果不报错）。`/api/v1/search` 已改走 `hybrid.hybrid_search`。首次运行的 1 项失败是测试把 `source_type` 放在请求体顶层而接口读取 `filters`，已改测试（接口按规格设计，未改）。接入后 `verify_v01.py` 回归 23/23 通过。
- [ ] 注意：语义近义用例（"汽车"命中"轿车"）使用的是手工构造的固定向量，只证明融合与退化逻辑，**不证明真实语义效果**；真实语义验收需 fastembed + bge-small-zh 实测（模型需联网下载，尚未做）。
- [x] 回归（V0.3 流水线加入向量化、/search 改走混合检索之后，用户环境实测）：`verify_v03.py` 22/22、`verify_v02.py` 20/20、`verify_v01.py` 23/23 全部通过。
- [x] V0.4（标签部分）已实测：`scripts/verify_v06.py` 17/17 通过（标签写入 1~8 个且来源标记 llm、排除无信息量词、`documents.tags` 展示字段同步、`tags.doc_count` 计数正确、重处理不产生重复标签、标签步骤故障转 failed 且摘要保留、失败时无标签残留且关键词检索仍可用、重试后写入标签、删除后 `document_tags` 无残留）。加入标签步骤后 `verify_v03.py` 22/22、`verify_v04.py` 27/27 回归通过；`verify_v02.py` 20/20、`verify_v05.py` 16/16、`verify_v01.py` 23/23 为标签步骤接入前的结果，下一步需整体重跑。过程中发现并删除了 `MockLLM` 里重复定义的 `tag` 方法。
- [ ] V0.4 仍未完成：fastembed + bge-small-zh 真实模型的语义检索实测（Mock 不能证明语义近义，需联网下载模型）。
- [x] 分类（对应计划中的 V0.5 两段式分类）已实测：`scripts/verify_v07.py` 27/27 通过（三级分类创建、逐级建父节点、深度>3 与单节点子分类>12 被拒绝、centroid 增量加入/精确移除并归一化、冷启动由 LLM 新建、第二篇经 centroid 候选筛选归入已有分类、doc_count 正确且重处理不重复计数、约束被突破时退回最相近候选并置 needs_review、冷启动无法新建落到系统「未分类」、分类故障转 failed 且摘要保留、重试后恢复）。过程中发现并修复一个算法缺陷：centroid 只存归一化向量，丢失模长，移除文档后无法精确还原；已改为另存未归一化的 `centroid_sum`，加减均在其上进行。
- [x] 分类接入后的整体回归（本机终端实测）：`verify_v01` 23/23、`verify_v02` 20/20、`verify_v03` 22/22、`verify_v04` 27/27、`verify_v05` 16/16、`verify_v06` 17/17、`verify_v07` 27/27。其中 `verify_v04` 首次回归有 1 项失败（"重试不重复调用 LLM"），原因：重试时分类步骤尚未完成，LLM 合理地多被调用一次，旧断言统计总调用次数已过时；已改为只断言摘要步骤不重复，未改实现。
- [ ] 注意：分类准确率与"两段式 vs 全量塞 prompt"的 token 对比属于评估实验（任务 8），当前使用 Mock LLM，只验证机制，不代表真实分类质量。
- [x] 管理接口（对应计划中的 V0.6）已实测：`scripts/verify_v08.py` 44/44 通过（含 DELETE /categories/{id}：含子分类与系统分类被拒绝、有文档须指定 migrate_to、空分类可删、迁移后文档归属正确、不存在返回 404）（PATCH 改标题并同步 FTS、空标题 400、不存在 404；改分类/改标签并写入 corrections、相同值不重复记录；用户标签 source=user 并替换旧 llm 标签；分类深度超限 400；标签列表；分类树查询；新建、重命名（同步 documents.category_path）、合并（文档迁移、源分类删除、doc_count 正确）、合并到自身/含子分类被拒绝；级联删除后切片/正文/FTS/document_tags 无残留，标签与分类 doc_count 回退）。`DELETE /documents/{id}` 已改走 `manage.delete_document_full`。
- [x] 管理接口接入后的整体回归（本机终端实测）：`verify_v01` 23/23、`verify_v02` 20/20、`verify_v03` 22/22、`verify_v04` 27/27、`verify_v05` 16/16、`verify_v06` 17/17、`verify_v07` 27/27 全部通过。
- [ ] 注意：corrections 目前只记录，不参与自动分类（规格中的"理想态"，留待后续）。`DELETE /categories/{id}` 与最小管理页已实现（见下方条目）。
- [x] 一键验证（本机实测）：`scripts/verify_all.py` 依次运行全部 verify 脚本，合计 **195 项通过 / 0 失败，9 个脚本**（floatbox 7、v01 23、v02 20、v03 22、v04 27、v05 16、v06 17、v07 27、v08 36）。
- [x] 安全（本机实测）：`scripts/verify_v09.py` 14/14 通过（可选 `KB_API_TOKEN`：未设置放行；设置后缺失/错误 `X-KB-Token` 返回 401 且为统一响应格式、正确放行；删除与检索接口同样受保护；`/health` 与 CORS 预检免校验；非法 Host 返回 403 防 DNS rebinding）。过程中发现 main.py 有两个重复的 token 中间件，已删除重复项。加入后一键验证 `verify_all.py` 合计 **217 项通过 / 0 失败，10 个脚本**（v08 已含 DELETE /categories 用例，共 44 项）。README 已更新。
- [ ] 注意：悬浮框尚未携带 `X-KB-Token`（设置 token 后悬浮框提交会 401），需在悬浮框提交逻辑中读取 `KB_API_TOKEN` 并加请求头。
- [x] 悬浮框携带 token 已实测：`floatbox/submit.py` 在设置 `KB_API_TOKEN` 时带 `X-KB-Token`，未设置时不带；`scripts/verify_floatbox.py` 由 7 项增至 9/9 通过。
- [x] 最小管理页已实测：`app/static/index.html` 由 `GET /` 提供，`scripts/verify_v10.py` 6/6 通过（返回 200 HTML、UTF-8 中文标题、页面调用检索与文档接口、API 不受影响）。**仅验证了路由与页面内容，未在真实浏览器中人工操作验收。** 加入后一键验证 `verify_all.py` 合计 **225 项通过 / 0 失败，11 个脚本**（floatbox 9、v01 23、v02 20、v03 22、v04 27、v05 16、v06 17、v07 27、v08 44、v09 14、v10 6）。
- [x] FTS5 分词对比实验（用户终端实测，语料 12 篇 / 查询 18 条，Recall@5 / MRR）：全部查询 unicode61 0.28、trigram 0.50、jieba 1.00；2 字词 unicode61 与 trigram 均为 0.00，jieba 为 1.00；≥3 字词 trigram 与 jieba 均为 1.00；英文专名三者均为 1.00。结论：中文关键词检索采用 jieba 预分词。小语料仅作机制对比，报告见 `评估报告_FTS分词对比.md`。
- [~] 悬浮框修复：`floatbox/app.py` 原为 `from submit import ...`，按 README 的 `python -m floatbox.app` 启动会 ModuleNotFoundError，已改为包内导入。窗口层自动化测试 `scripts/verify_floatbox_ui.py`（Qt 离屏）已由用户在终端实测：**16/16 通过**（字数统计、成功后清空/绿色提示/收起、失败后保留文本/红色提示/不收起、Ctrl+Enter、Esc、热键解析、RegisterHotKey 注册与注销、WM_HOTKEY 回调）。
- [x] 悬浮框真实端到端（本机自动实测）：`scripts/verify_floatbox_e2e.py` **6/6 通过**。用临时库启动后端与悬浮框，以记事本作为第三方前台应用，用 SendInput 模拟真实 Ctrl+Alt+K：悬浮框成为前台窗口（热键+焦点）、键入文本后 Ctrl+Enter 数据库新增 float_window 文档、正文一致、成功后悬浮框收起。首次运行 1 项失败，原因是测试把 venv 启动器的 pid 当作窗口进程 pid，已改为按前台进程可执行文件名判断（测试逻辑修正，非产品缺陷）。
- [x] 语义检索实测（用户终端，bge-small-zh-v1.5 via fastembed）：近义（用词不同）组 Recall@3/MRR：词面重叠 0.56/0.57，Mock 哈希词袋 0.56/0.54，bge-small-zh **1.00/1.00**；字面组三者均 1.00。小语料（12 篇、12 查询）仅作机制对比。
- [x] 管理页浏览器自动化（用户终端实测）：`scripts/verify_admin_ui.py`（playwright + 本机 Edge）9/9 通过，覆盖列表、搜索、详情、改标题/分类/标签、删除、无 JS 报错。过程中发现并修复两处真实界面缺陷：`save()`/`del()` 先显示"已保存/已删除"，随后被 `loadList()` 的"加载中…"覆盖，用户看不到操作反馈；现改为等列表刷新后再提示。修复后未重跑 `verify_v10.py` 与一键验证，待回归。
- [~] 真实语义检索评估脚本 `scripts/eval_semantic.py` 已写好（对比 Mock 哈希词袋与 bge-small-zh），**尚未运行**，需联网下载模型，由用户在终端运行。
- [x] 前端开源项目调研（经代理后 WebFetch 可访问 GitHub）：候选 HiAi-gg/docsmint（Apache-2.0，SvelteKit + Svelte 5 + Tailwind，含 SearchBar / DocumentCard / FolderTreeSelector / TagCreateDialog 等组件）。结论：组件依赖 SvelteKit、内部 UI 库与宿主路由适配器，迁移成本高于重写，且会引入 Node 构建链；本项目保持单文件静态页，仅借鉴展示逻辑（去 Markdown 后截取摘要、最多显示 3 个标签并以 +N 折叠、相对时间）。详见 `核实报告.md` 第五节。
- [x] 管理页浏览器自动化 verify_admin_ui.py 9/9 通过；悬浮框 verify_floatbox_ui.py 16/16、verify_floatbox_e2e.py 6/6 通过；eval_semantic.py 已由用户运行（近义组 bge-small-zh Recall@3 为 1.00，词面重叠与 Mock 均为 0.56）。
- [ ] 后续：在 `app/static/index.html` 的 `row()` 中落地上述三项展示改进并补管理页验收用例；把 eval_semantic.py 数据写入评估报告；评估报告其余章节；README 补充代理配置说明。
- [ ] markitdown 未被 V0.2 采用（解析器直接用 pdfplumber / python-docx / openpyxl 以便控制扫描件判空与 sheet 分区），其功能实测降为可选对照实验。

### V0.1 验证状态（用户在终端实测）
- [x] `verify_floatbox.py`：7 通过 / 0 失败（成功提交、HTTP 500、后端未启动保留文本、空文本不发请求等）。
- [~] `verify_v01.py`：22 通过 / 1 失败。失败项为"无结果不报错"，原因判断为测试数据问题：`zzzqqq不存在` 经 jieba 切出"存在"，OR 档命中了其他文档。已把用例改为完全无关的字符串，**尚未重跑，不记为通过**。
- [ ] 待用户重跑：`venv\Scripts\python.exe scripts\verify_v01.py`，期望 23/23。
- [ ] 悬浮框人工验收（热键唤起聚焦、Ctrl+Enter 入库、后端关闭时文本不丢）尚未做。
- 补充：venv 原先缺 fastapi / uvicorn / python-multipart / PySide6，现已按 `requirements.txt` 装好。

## 五、风险前置

1. Windows 热键与前台焦点：V0.1 即做 PoC，失败则降级为"托盘点击唤起"。
2. FTS5 中文方案：V0.1 用 jieba 预分词，V1.0 评估实验对比 unicode61 / trigram / jieba / simple。
