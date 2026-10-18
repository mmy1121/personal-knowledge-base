C:\Users\User\Desktop\111\work\scripts\eval_classify_stability.py:4: SyntaxWarning: invalid escape sequence '\S'
  venv\Scripts\python.exe -I -X utf8 scripts\eval_classify_stability.py
Building prefix dict from the default dictionary ...
Loading model from cache C:\Users\User\AppData\Local\Temp\jieba.cache
Loading model cost 0.839 seconds.
Prefix dict has been built successfully.
# S02 分类稳定性评估（LLM=mock，Embedding=mock）

文档 20 篇，主题 5 个，单次运行，无置信区间。

- 创建分类数：13（理想≈5，越大越说明过度新增）
- 复用已有分类：8/15 = 0.53
- needs_review：8 篇

| 主题 | 同类聚合度 | 分类分布 |
|---|---|---|
| 数据库 | 0.50 | {'通用/关系': 2, '通用/SQLite': 1, '通用/向量': 1} |
| 烹饪 | 0.50 | {'通用/红烧': 2, '通用/米饭': 1, '通用/炒青': 1} |
| 健身 | 0.50 | {'通用/每周': 1, '通用/硬拉是': 2, '通用/分散': 1} |
| 旅行 | 0.50 | {'通用/海边': 2, '通用/东京': 1, '通用/硬拉是': 1} |
| 理财 | 0.25 | {'通用/分散': 1, '通用/长期': 1, '通用/米饭': 1, '通用/SQLite': 1} |

全部分类：通用、通用/SQLite、通用/东京、通用/关系、通用/分散、通用/向量、通用/每周、通用/海边、通用/炒青、通用/硬拉是、通用/米饭、通用/红烧、通用/长期

说明：Mock LLM/哈希向量只验证机制，不代表真实模型的分类稳定性；真实结论需用 deepseek + fastembed 复跑并另行标注。
