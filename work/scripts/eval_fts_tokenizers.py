"""评估实验 1：FTS5 中文分词方案对关键词检索召回的影响。

对比三种方案：
- unicode61：原文直接入库（中文整句成一个 token）
- trigram：SQLite 内置，查询词需 >= 3 字符
- jieba：入库与查询共用 jieba 搜索模式预分词（本项目默认方案）
指标：Recall@5、MRR，按查询词长度（2 字 / >=3 字 / 英文专有名词）分组。
运行：venv/Scripts/python.exe scripts/eval_fts_tokenizers.py
结果同时写入 ../评估结果_FTS分词.md
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import db  # noqa: E402

CORPUS = {
    1: "向量数据库选型：对比 ChromaDB 与 Qdrant 的性能和部署成本",
    2: "文档自动分类依赖向量相似度筛选候选分类，再由大模型定夺",
    3: "SQLite 全文索引 FTS5 对中文需要额外分词处理",
    4: "周末计划：去爬山看日出，带上相机和保温杯",
    5: "FastAPI 后端接口设计：统一响应格式与错误处理",
    6: "悬浮框快捷录入：全局热键唤起，粘贴后 Ctrl+Enter 存入",
    7: "标签生成要求提取三到八个短名词，排除无信息量的词",
    8: "混合检索使用 RRF 融合关键词排名与语义排名",
    9: "扫描版 PDF 没有文本层，需要 OCR 才能提取文字",
    10: "课程设计报告需要包含需求分析、系统设计、实现与评估",
    11: "汽车保养手册：定期更换机油与滤芯",
    12: "笔记本电脑选购指南：内存与固态硬盘容量建议",
}
# (查询, 相关文档集合, 分组)
QUERIES = [
    ("分类", {2}, "2字词"), ("索引", {3}, "2字词"), ("分词", {3}, "2字词"),
    ("热键", {6}, "2字词"), ("标签", {7}, "2字词"), ("检索", {8}, "2字词"),
    ("评估", {10}, "2字词"), ("接口", {5}, "2字词"), ("爬山", {4}, "2字词"),
    ("向量数据库", {1}, ">=3字词"), ("全文索引", {3}, ">=3字词"),
    ("文本层", {9}, ">=3字词"), ("悬浮框", {6}, ">=3字词"), ("统一响应", {5}, ">=3字词"),
    ("ChromaDB", {1}, "英文专名"), ("FastAPI", {5}, "英文专名"),
    ("RRF", {8}, "英文专名"), ("OCR", {9}, "英文专名"),
]


def build(mode: str):
    c = sqlite3.connect(":memory:")
    if mode == "trigram":
        c.execute("CREATE VIRTUAL TABLE f USING fts5(t, tokenize='trigram')")
    else:
        c.execute("CREATE VIRTUAL TABLE f USING fts5(t, tokenize='unicode61')")
    for i, t in CORPUS.items():
        c.execute("INSERT INTO f(rowid, t) VALUES(?,?)", (i, db.seg(t) if mode == "jieba" else t))
    return c


def search(c, mode: str, q: str):
    if mode == "jieba":
        terms = list(dict.fromkeys(db.tokenize(q)))
        if not terms:
            return []
        match = " OR ".join('"%s"' % t for t in terms)
    else:
        match = '"%s"' % q
    try:
        return [r[0] for r in c.execute(
            "SELECT rowid FROM f WHERE f MATCH ? ORDER BY bm25(f) LIMIT 5", (match,))]
    except sqlite3.OperationalError:
        return []


def main():
    modes = ["unicode61", "trigram", "jieba"]
    groups = ["2字词", ">=3字词", "英文专名"]
    res = {}
    for m in modes:
        c = build(m)
        for g in groups + ["全部"]:
            qs = [x for x in QUERIES if g == "全部" or x[2] == g]
            hit, rr = 0, 0.0
            for q, rel, _ in qs:
                ids = search(c, m, q)
                if any(i in rel for i in ids):
                    hit += 1
                for rank, i in enumerate(ids, 1):
                    if i in rel:
                        rr += 1.0 / rank
                        break
            res[(m, g)] = (hit / len(qs), rr / len(qs), len(qs))
    lines = ["# 评估结果：FTS5 中文分词方案对比", "",
             "语料 %d 篇，查询 %d 条。指标：Recall@5 / MRR。" % (len(CORPUS), len(QUERIES)), "",
             "| 分组(查询数) | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for g in groups + ["全部"]:
        n = res[(modes[0], g)][2]
        cells = ["%.2f / %.2f" % res[(m, g)][:2] for m in modes]
        lines.append("| %s(%d) | %s |" % (g, n, " | ".join(cells)))
    lines += ["", "说明：小语料仅用于机制对比，不代表大规模数据表现；jieba 方案使用 OR 档查询。"]
    out = "\n".join(lines)
    print(out)
    path = os.path.join(os.path.dirname(ROOT), "评估结果_FTS分词.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    main()
